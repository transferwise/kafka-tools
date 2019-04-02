Kafka Tools
===========

This repository is an internal clone of kafka-tools project developed and open sourced by LinkedIn https://github.com/linkedin/kafka-tools

Original kafka-tools documentation may be found at `https://kafka-tools.readthedocs.io <https://kafka-tools.readthedocs.io/en/latest/>`_.

Quick Start
-----------

1) Make sure python 3 is installed
2) Download the Kafka admin utilities: http://kafka.apache.org/downloads.html
3) Install TransferWise internal kafka-tools using the following commands:
    :code:`git clone git@github.com:transferwise/kafka-tools.git`
    :code:`cd kafka-tools`
    :code:`pip3 install -e .`


Migration of topics to AWS
--------------------------

Background: We have a hybrid kafka cluster currently with broker nodes both in LeaseWeb and AWS

Objective: We want to migrate all topic partitions, partition leadership and partition replicas entirely to AWS and retire broker nodes in LeaseWeb

Code structure: The original kafka-tools project allows us to bring about changes to cluster configurations through actions. Some of the actions are clone, trim, set-replication-factor etc

Custom actions: We have modified actions and some core classes to achieve the objective (above)


Driver script
-------------
The driver script will be used by simply executing :code:`migrate_to_aws.sh`. It will work as follows

We will create a special topic called *topics_migrated* and initially it won't contain any topics.

The script won't have any assumptions about the start state, it could be that all topics need to be migrated and it could be that everything is migrated already.

Script will do two following ...

1. Get the list of all topics in kafka cluster
2. Get the list of topics migrated from *topics_migrated* topic

Subtracting 2 from 1, we will get the list of topics yet to be migrated and script will migrate the topics one by one and with each migrate write the topic name as a message to *topics_migrated* topic

The topics will be migrated using the actions described in further sections

We can migrate all topics list received with (2-1) at once but to limit the data migration per day/per invocation etc., we will migrate only a limited number of topics each day and run script over multiple days to migrate all topics

Even if the script processes same topic twice due to some failures/issues, there's no side-effects as it would just result in a no-op (no state change in cluster for that topic)

Once the list of topics in 1 and 2 are same, (2-1) will return an empty list and we can expect all topics have been safely migrated in AWS and we can look to retire LW brokers after that.

Once all LW brokers are retired, the script execution/schedule will be stopped and it can be retired safely.

As a last cleanup step, we can also delete *topics_migrated* topic from the cluster


Description for the actions
---------------------------

clone: This action expects the list of aws brokers and lw brokers and a set of topics and as an end result migrate the leadership of topic's partitions to AWS. It might create, if needed, a new replica in AWS

set-replication-factor: This action expects the list of aws brokers, set of topics and a target replication factor and creates a new replica if current replication factor is less than target.

trim: This action expects the list of lw brokers and set of topics and reduce one replica of topic partition on lw brokers if possible (not possible when no replicas present on lw)

Important note: The actions will only make any real changes to cluster when the kafka-assigner command (the main command for all actions) has --execute flag

Running the actions (staging cluster)
-------------------------------------

Note: We will provide a driver script to run these actions automatically and the script will only expect the input as target replication factor and list of topics

Can run the actions locally or from test-kafka-tools.tw.ee, the commands given below are for test-kafka-tools.tw.ee

Let's say we create a topic kafka-test with 6 partitions and 3 replicas

:code:`./kafka-topics.sh --zookeeper kafka1.tw.ee:2181,kafka2.tw.ee:2181,kafka3.tw.ee:2181 --create --topic kafka-test --partitions 6 --replication-factor 3`

Describing the topic might look something like this

:code:`./kafka-topics.sh --zookeeper kafka1.tw.ee:2181,kafka2.tw.ee:2181,kafka3.tw.ee:2181 --describe --topic kafka-test`

::
Topic:kafka-test	PartitionCount:6	ReplicationFactor:3	Configs:
	Topic: kafka-test	Partition: 0	Leader: 6	Replicas: 6,7,8	Isr: 6,7,8
	Topic: kafka-test	Partition: 1	Leader: 7	Replicas: 7,8,1001	Isr: 7,8,1001
	Topic: kafka-test	Partition: 2	Leader: 8	Replicas: 8,1001,1002	Isr: 8,1001,1002
	Topic: kafka-test	Partition: 3	Leader: 1001	Replicas: 1001,1002,1003	Isr: 1001,1002,1003
	Topic: kafka-test	Partition: 4	Leader: 1002	Replicas: 1002,1003,1	Isr: 1002,1003,1
	Topic: kafka-test	Partition: 5	Leader: 1003	Replicas: 1003,1,2	Isr: 1003,1,2


As we can see here, for partitions 0,1,2 the leader is in LW while for 3,4,5 the leader is in AWS

We will first run the clone action to migrate leadership to AWS

:code:`kafka-assigner -z kafka1.tw.ee:2181,kafka2.tw.ee:2181,kafka3.tw.ee:2181 --tools-path /home/ansible/kafka/bin --execute clone --brokers 1 2 3 4 5 6 7 8 --to_broker  1001 1002 1003 --topics kafka-test`


After running the clone action, the topic describe might look something like this, notice all partitions leaders are now AWS brokers. Also the step might end up having 3 or 4 replicas for a partition

::
Topic:kafka-test	PartitionCount:6	ReplicationFactor:4	Configs:
	Topic: kafka-test	Partition: 0	Leader: 1002	Replicas: 1002,6,7,8	Isr: 6,7,8,1002
	Topic: kafka-test	Partition: 1	Leader: 1003	Replicas: 1003,7,8,1001	Isr: 7,8,1001,1003
	Topic: kafka-test	Partition: 2	Leader: 1002	Replicas: 1002,1001,8	Isr: 8,1001,1002
	Topic: kafka-test	Partition: 3	Leader: 1001	Replicas: 1001,1002,1003	Isr: 1001,1002,1003
	Topic: kafka-test	Partition: 4	Leader: 1003	Replicas: 1003,1002,1	Isr: 1002,1003,1
	Topic: kafka-test	Partition: 5	Leader: 1003	Replicas: 1003,1001,1,2	Isr: 1003,1,2,1001

Next we will run set-replication-factor action to add more replicas to aws and then trim a replica from lw,

We might need to run these two steps couple of times (set-replication-factor, trim, set-replication-factor, trim ...) depending on target replication factor. This order of actions is preferable to keep the total replica count in check

:code:`kafka-assigner -z kafka1.tw.ee:2181,kafka2.tw.ee:2181,kafka3.tw.ee:2181 --tools-path /home/ansible/kafka/bin --execute set-replication-factor --replicate_to_aws_brokers 1003 1001 1002  --topics kafka-test --replication-factor 3`
:code:`kafka-assigner -z kafka1.tw.ee:2181,kafka2.tw.ee:2181,kafka3.tw.ee:2181 --tools-path /home/ansible/kafka/bin --execute trim --remove_from_lw_brokers 8 7 3 1 5 6 4 2  --topics kafka-test`

Finally, only where needed, after we have target replica count in AWS, we can trim any remaining LW replicas by running
:code:`kafka-assigner -z kafka1.tw.ee:2181,kafka2.tw.ee:2181,kafka3.tw.ee:2181 --tools-path /home/ansible/kafka/bin --execute trim --remove_from_lw_brokers 8 7 3 1 5 6 4 2  --topics kafka-test`


Deleting the test topic after above actions are executed (staging cluster)
--------------------------------------------------------------------------

./kafka-topics.sh --zookeeper kafka1.tw.ee:2181,kafka2.tw.ee:2181,kafka3.tw.ee:2181 --topic kafka-test --delete




