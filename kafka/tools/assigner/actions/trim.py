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

from kafka.tools import log
from kafka.tools.assigner.actions import ActionModule
from kafka.tools.exceptions import NotEnoughReplicasException
from kafka.tools.exceptions import ConfigurationException


class ActionTrim(ActionModule):
    name = "trim"
    helpstr = "Remove partition replica from some broker in LeaseWeb (reducing RF)"

    def __init__(self, args, cluster):
        super(ActionTrim, self).__init__(args, cluster)

        self.from_lw_brokers = args.remove_from_lw_brokers
        for from_lw_broker in self.from_lw_brokers:
            if self.cluster.brokers[from_lw_broker] is None:
                raise ConfigurationException("LW broker specified is not in the brokers list for this cluster")

    @classmethod
    def _add_args(cls, parser):
        # for our requirement, this is expected to be brokers in LW
        parser.add_argument('-d', '--remove_from_lw_brokers', help="List of  lw broker ids to trim replicas from",
                            required=True, type=int,
                            nargs='*')

        parser.add_argument('-t', '--topics', help='List of topics to run the trim action',
                            required=True, nargs='*')

    def process_cluster(self):
        for partition in self.cluster.partitions_for(self.args.topics):
            log.info("lw replica trimming starting for partition num {0} of topic {1}".format(partition.num, partition.topic.name))
            lw_broker_replicas = self.cluster.get_replicas_for(partition, self.from_lw_brokers)
            partition.remove_lw_replica(lw_broker_replicas)
            if len(partition.replicas) < 1:
                raise NotEnoughReplicasException(
                    "Cannot trim {0}:{1} as it would result in an empty replica list".format(
                        partition.topic.name, partition.num))
