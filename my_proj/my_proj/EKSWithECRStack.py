from aws_cdk import (
    aws_ec2 as ec2,
    aws_eks as eks,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_secretsmanager as secretsmanager,
    aws_rds as rds,
    aws_cloudwatch as cloudwatch,
)

import aws_cdk as core
from constructs import Construct

class EksWithEcrStack(core.Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # 创建 VPC
        vpc = ec2.Vpc(self, "MyVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                ),
                ec2.SubnetConfiguration(
                    name="PrivateSubnet",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                ),
            ]
        )

        # 创建 ECR 存储库
        ecr_repository_names = ["redis", "httpd", "email"]
        ecr_repositories = {}
        for repo_name in ecr_repository_names:
            ecr_repositories[repo_name] = ecr.Repository(self, f"{repo_name}Repository")

        # 创建 EKS 集群
        cluster = eks.Cluster(self, "MyCluster",
            vpc=vpc,
            default_capacity=0
        )

        # 为 Fargate 添加 IAM 角色权限
        cluster.add_to_principal_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ecr:GetAuthorizationToken", "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=["*"]
        ))

        # 创建 Fargate Profile
        for repo_name, ecr_repo in ecr_repositories.items():
            cluster.add_fargate_profile(f"{repo_name}FargateProfile",
                selectors=[{
                    "namespace": "default",
                    "labels": {"app": repo_name}
                }]
            )

        # 创建 Application Load Balancer
        alb = ecs_patterns.ApplicationLoadBalancedFargateService(self, "MyFargateService",
            cluster=cluster,
            task_image_options=[
                ecs_patterns.ApplicationLoadBalancedTaskImageOptions(image=ecs.ContainerImage.from_ecr_repository(ecr_repositories["redis"]), container_port=6379),
                ecs_patterns.ApplicationLoadBalancedTaskImageOptions(image=ecs.ContainerImage.from_ecr_repository(ecr_repositories["httpd"]), container_port=80),
                ecs_patterns.ApplicationLoadBalancedTaskImageOptions(image=ecs.ContainerImage.from_ecr_repository(ecr_repositories["email"]), container_port=80),
            ],
            public_load_balancer=True,
            desired_count=1,
        )

        # 创建 AutoScaling Group
        scaling = alb.service.auto_scale_task_count(max_capacity=10)
        scaling.scale_on_cpu_utilization("CpuScaling", target_utilization_percent=50)
        self.s3_data_ops()
        self.aurora_data_ops()
        # 监控 Fargate 服务的 CPU 和内存利用率
        self.add_cloudwatch_metrics()

    def create_s3_lambda(self):
        # 创建 Lambda 函数
        s3_lambda = _lambda.Function(
            self, "MyS3LambdaFunction",
            runtime=_lambda.Runtime.PYTHON_3_8,
            handler="lambda_function.handler",
            code=_lambda.Code.from_asset("D://Documents/pythonProject/aws/my_proj/lambda_fun/fun_s3/"),  # 指定 Lambda 函数代码路径
            environment={
                'BUCKET_NAME': 'mybucket-cdk'
            }
        )

        # 添加 Lambda 执行角色权限
        s3_lambda.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=["arn:aws:s3:::mybucket-cdk/*"]  # S3 存储桶 ARN
            )
        )

        return s3_lambda

    def create_aurora_writer_lambda(self, cluster):

        # 从 Secrets Manager 中获取 Aurora 数据库的登录信息
        db_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "MyDBSecret",
            secret_name="my-db-secret"
        )

        # 数据库表
        database_name = "my_database"

        # database_credentials = secretsmanager.Secret(
        #     self, "DatabaseCredentials",
        #     generate_secret_string=secretsmanager.SecretStringGenerator(
        #         secret_string_template='{"username": "admin"}',
        #         generate_string_key='password',
        #         exclude_punctuation=True
        #     )
        # )

        # database_credentials.grant_read_write(cluster.secret.secret_arn)

        # 创建 Lambda 函数
        aurora_lambda = _lambda.Function(
            self, "MyAuroraLambdaFunction",
            runtime=_lambda.Runtime.PYTHON_3_8,
            handler="lambda_function.handler",
            code=_lambda.Code.from_asset("D://Documents/pythonProject/aws/my_proj/lambda_fun/fun_aurora/"),
            environment={
                'DATABASE_ENDPOINT': cluster.cluster_endpoint.hostname,
                'DATABASE_NAME': database_name,
                'DATABASE_SECRET_ARN': db_secret.secret_arn  # 使用 Secrets Manager 中的 ARN
            }
        )

        db_secret.grant_read(aurora_lambda)

        # 添加 Lambda 执行角色权限
        aurora_lambda.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue", "rds-data:ExecuteStatement"],
                resources=[db_secret.secret_arn]  # 允许 Lambda 访问 Secrets Manager 中的特定 secret
            )
        )

        return aurora_lambda

    def s3_data_ops(self):
        # 创建 S3 存储桶
        bucket = s3.Bucket(
            self, "mybucket-cdk",
            removal_policy=core.RemovalPolicy.DESTROY
        )

        s3_lambda_function = self.create_s3_lambda()

        # 添加 Lambda 函数的 IAM 权限
        bucket.grant_write(s3_lambda_function)

        # 将 Lambda 函数绑定到事件源，以便在容器完成后触发
        rule = events.Rule(
            self, "MyS3Rule",
            event_pattern={
                "source": ["aws.ecs"],
                "detail": {
                    "lastStatus": ["STOPPED"]
                }
            }
        )
        rule.add_target(targets.LambdaFunction(s3_lambda_function))

    def aurora_data_ops(self):
        # 创建 Amazon Aurora 数据库
        cluster = rds.DatabaseCluster(
            self, "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_mysql(
                version=rds.AuroraMysqlEngineVersion.VER_2_11_2
            ),
            instance_props={
                "instance_type": ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE2, ec2.InstanceSize.SMALL),
                "vpc_subnets": {
                    "subnet_type": ec2.SubnetType.PRIVATE_ISOLATED
                },
                "vpc": self.vpc
            },
            parameter_group=rds.ParameterGroup.from_parameter_group_name(
                self, "ParameterGroup",
                parameter_group_name="default.aurora-mysql5.7"
            )
        )

        # 创建 Lambda 函数
        lambda_function = self.create_aurora_writer_lambda(cluster)

        # 创建 Lambda 函数的触发器，使其能够响应特定事件并将数据写入数据库
        rule = events.Rule(
            self, "MyAuroraRule",
            event_pattern={
                "source": ["aws.ecs"],
                "detail": {
                    "lastStatus": ["STOPPED"]
                }
            }
        )
        rule.add_target(targets.LambdaFunction(lambda_function))

    def add_cloudwatch_metrics(self):
        # 监控 Fargate 服务的 CPU 利用率
        cpu_metric = cloudwatch.Metric(
            namespace="AWS/ECS",
            metric_name="CPUUtilization",
            dimensions={
                "ClusterName": "MyCluster",  # 更改为您的集群名称
                "ServiceName": "MyFargateService"  # 更改为您的服务名称
            },
            statistic="Average",
            period=core.Duration.minutes(5)
        )

        # 创建 CloudWatch 报警以监控 CPU 利用率
        cpu_alarm = cloudwatch.Alarm(
            self, "FargateCPUAlarm",
            metric=cpu_metric,
            threshold=80,  # CPU 利用率阈值（此处为 80%）
            evaluation_periods=1,
            alarm_name="FargateCPUAlarm",
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            actions_enabled=True,
            alarm_description="Alarm when Fargate CPU exceeds 80%",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING  # 在缺失数据时不触发报警
        )

        # 监控 Fargate 服务的内存利用率
        memory_metric = cloudwatch.Metric(
            namespace="AWS/ECS",
            metric_name="MemoryUtilization",
            dimensions={
                "ClusterName": "MyCluster",  # 更改为您的集群名称
                "ServiceName": "MyFargateService"  # 更改为您的服务名称
            },
            statistic="Average",
            period=core.Duration.minutes(5)
        )

        # 创建 CloudWatch 报警以监控内存利用率
        memory_alarm = cloudwatch.Alarm(
            self, "FargateMemoryAlarm",
            metric=memory_metric,
            threshold=80,  # 内存利用率阈值（此处为 80%）
            evaluation_periods=1,
            alarm_name="FargateMemoryAlarm",
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            actions_enabled=True,
            alarm_description="Alarm when Fargate memory exceeds 80%",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING  # 在缺失数据时不触发报警
        )