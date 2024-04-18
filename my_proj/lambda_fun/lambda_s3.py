import boto3
import json
import os


def handler(event, context):
    # 从环境变量中获取 S3 存储桶名称
    bucket_name = os.environ['BUCKET_NAME']

    # 初始化 S3 客户端
    s3 = boto3.client('s3')

    # 示例：假设触发 Lambda 函数的事件是 JSON 格式的数据
    event_data = json.loads(event['body'])

    # 将数据写入到 S3 中
    try:
        response = s3.put_object(
            Bucket=bucket_name,
            Key='example.json',  # 指定对象键
            Body=json.dumps(event_data)  # 将数据转换为 JSON 格式并写入对象
        )
        print(response)
        return {
            'statusCode': 200,
            'body': json.dumps('Data written to S3 successfully!')
        }
    except Exception as e:
        print(e)
        return {
            'statusCode': 500,
            'body': json.dumps('Error writing data to S3')
        }
