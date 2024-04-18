import json
import boto3
import pymysql


# 从 AWS Secrets Manager 中获取数据库凭据
def get_database_credentials():
    client = boto3.client('secretsmanager')
    secret_name = "your-secret-name"
    response = client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response['SecretString'])
    return secret['username'], secret['password']


# 从服务获取数据的示例函数
def get_data_from_service(event):
    # 这里假设你有一个可以获取数据的函数或 API 调用
    # 这里只是一个示例，你需要根据实际情况来实现
    return json.loads(event['body'])
    # return {"data": "example data"}


# 写入数据到 Amazon Aurora 数据库
def write_to_aurora(data):
    # 获取数据库凭据
    username, password = get_database_credentials()

    # 连接到数据库
    try:
        conn = pymysql.connect(
            host='your-database-endpoint',
            user=username,
            password=password,
            db='your-database-name',
            connect_timeout=5
        )

        # 创建游标对象
        cursor = conn.cursor()

        # 执行插入数据的 SQL 命令
        sql = "INSERT INTO your_table_name (column1, column2) VALUES (%s, %s)"
        cursor.execute(sql, (data['value1'], data['value2']))

        # 提交事务
        conn.commit()

    except Exception as e:
        print("Error:", e)
        conn.rollback()

    finally:
        # 关闭数据库连接
        cursor.close()
        conn.close()


def lambda_handler(event, context):
    # 从服务获取数据
    data = get_data_from_service(event)

    # 将数据写入 Amazon Aurora 数据库
    write_to_aurora(data)

    return {
        'statusCode': 200,
        'body': json.dumps('Data successfully written to Aurora!')
    }
