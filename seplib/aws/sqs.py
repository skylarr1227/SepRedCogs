import boto3

class SQS(object):

    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str, region='us-east-1'):
        self._session = boto3.session.Session(aws_access_key_id=aws_access_key_id,
                                              aws_secret_access_key=aws_secret_access_key,
                                              region_name=region)

        self._queue_map = {}

        self._sqs = self._session.resource('sqs')

    def get_queue(self, queue_name: str):
        if queue_name in self._queue_map:
            return self._queue_map.get(queue_name)
        queue = self._sqs.get_queue_by_name(QueueName=queue_name)
        self._queue_map[queue_name] = queue
        return queue

    def send_message(self, queue_name: str, body: str):
        queue = self.get_queue(queue_name)
        return queue.send_message(MessageBody=body)
