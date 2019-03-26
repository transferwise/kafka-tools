# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import random
from kafka.tools import log
from collections import deque
from kafka.tools.assigner.actions import ActionModule
from kafka.tools.exceptions import ConfigurationException


class ActionSetRF(ActionModule):
    name = "set-replication-factor"
    helpstr = "given leader in aws, achieve a target replication factor by adding/removing replicas in aws/lw env respectively"

    def __init__(self, args, cluster):
        super(ActionSetRF, self).__init__(args, cluster)
        if args.replication_factor <= 2:
            raise ConfigurationException("You cannot set replication-factor below 3")

        self.MAX_RETRIES = 100

        self.target_rf = self.args.replication_factor

        self.to_aws_brokers = args.replicate_to_aws_brokers
        for to_aws_broker in self.to_aws_brokers:
            if self.cluster.brokers[to_aws_broker] is None:
                raise ConfigurationException("AWS broker specified is not in the brokers list for this cluster")

        if self.target_rf > len(self.to_aws_brokers):
            raise ConfigurationException("You cannot set replication-factor greater than the number of AWS brokers in the cluster")

    @classmethod
    def _add_args(cls, parser):
        parser.add_argument('-t', '--topics', help='List of topics to run the set-replication-factor action', required=True, nargs='*')
        parser.add_argument('-r', '--replication-factor', help='Target replication factor', required=True, type=int)


        # the list of broker ids in aws
        parser.add_argument('-p', '--replicate_to_aws_brokers', help="List of all broker id to be considered for adding new replicas", required=True, type=int,
                            nargs='*')

    def process_cluster(self):

        log.info("processing starts for set-replication-factor action")

        target_broker_list = list(self.to_aws_brokers)  # TODO handle duplicates?
        random.shuffle(target_broker_list)
        aws_brokers = deque(target_broker_list)

        for partition in self.cluster.partitions_for(self.args.topics):
            # TODO add check - partition leader should be in AWS, throw error to run clone action first to change leadership if not the case

            log.info("processing starts for partition num {0} of topic {1}".format(partition.num, partition.topic.name))
            retries = 0
            aws_broker_replicas = self.cluster.get_replicas_for(partition, target_broker_list)
            added_replica = False
            if len(aws_broker_replicas) < self.target_rf:
                while added_replica is not True:
                    broker = self.get_target_broker(aws_brokers)
                    if broker in partition.replicas:
                        if retries > self.MAX_RETRIES:
                            raise ConfigurationException("Too many attempts already, some configuration error in achieving target replication factor")
                        retries += 1
                        continue
                    else:
                        log.info("adding a replica for partition num {0} of topic {1} on broker {2}".format(partition.num, partition.topic.name, broker.id))
                        partition.add_aws_replica(broker)
                        added_replica = True
            else:
                log.info("partition num {0} of topic {1} already has {2} replicas".format(partition.num, partition.topic.name, self.target_rf))


    # Randomize a broker list to use for new replicas once. we'll just do round robin for now
    def get_target_broker(self, brokers):
        broker_id = brokers.popleft()
        brokers.append(broker_id)
        broker = self.cluster.brokers[broker_id]
        return broker
