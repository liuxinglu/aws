from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_rds as rds
)
import aws_cdk as core
from constructs import Construct

VPC_CIDR = "172.32.0.0/16"
SUBNET_SIZE = 26
SUBNET_CIDRS = ['172.32.1.0/24', '172.32.2.0/24']
AV_ZONES = ['ap-southeast-2a', 'ap-southeast-2b']

class EcsFargateStack(core.Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # 创建 VPC 和子网
        self.vpc = self.create_VPC()

        # 创建 NAT Gateway
        nat_gateway = ec2.CfnNatGateway(
            self, "MyNatGateway",
            allocation_id=ec2.CfnEIP(self, "EIP", domain="vpc").attr_allocation_id,
            subnet_id=self.vpc.select_subnets(subnet_type=ec2.SubnetType.PUBLIC).subnet_ids[0]
        )

        # 将私有子网的路由表设置为使用 NAT Gateway 作为默认路由
        private_subnet = self.vpc.private_subnets[0]
        route_table = private_subnet.route_table
        # 创建默认路由
        ec2.CfnRoute(
            self, "DefaultRouteToNat",
            route_table_id=route_table.route_table_id,
            destination_cidr_block="0.0.0.0/0",
            nat_gateway_id=nat_gateway.ref
        )

        # 定义 ECS 集群
        cluster = ecs.Cluster(
            self, "MyCluster",
            vpc=self.vpc
        )

        task_definition = ecs.FargateTaskDefinition(
            self, "taskDefinition"
        )
        for i in range(3):
            task_definition = self.get_image_to_task_container(task_definition, 'MyRepo' + str(i+1), "lastest", 'MyContainer' + str(i+1), 'MyLogGroup' + str(i+1))

        # 创建 ECS Service
        service = ecs.FargateService(
            self, "MyFargateService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=1, # 1个任务实例
            assign_public_ip=False,  # 不分配公有 IP，私有子网
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[self.create_fargate_SG()]
        )

        # 添加 AutoScaling
        scaling = service.auto_scale_task_count(
            min_capacity=3,
            max_capacity=5
        )

        # 创建 Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(
            self, "MyALB",
            vpc=self.vpc,
            internet_facing=True
        )

        # 添加 Target Group
        target_group = elbv2.ApplicationTargetGroup(
            self, "MyTargetGroup",
            vpc=self.vpc,
            port=80,
            targets=[service]
        )

        # 添加 Listener，并将 Target Group 关联
        listener = alb.add_listener(
            "MyListener",
            port=80,
            open=True,
            default_target_groups=[target_group]
        )

        self.s3_data_ops()
        self.aurora_data_ops()

        # 输出 ALB DNS 名称
        output = core.CfnOutput(
            self, "MyALBDNS",
            value=alb.load_balancer_dns_name
        )


    def create_VPC(self):
        vpc = ec2.Vpc(
            self,
            "MyVpc",
            ip_addresses = ec2.IpAddresses.cidr(VPC_CIDR),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public-Subnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=SUBNET_SIZE,
                ),
                ec2.SubnetConfiguration(
                    name="Private-Subnet-1",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=SUBNET_SIZE,
                ),
                ec2.SubnetConfiguration(
                    name="Private-Subnet-2",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=SUBNET_SIZE,
                ),
            ],
            availability_zones = [AV_ZONES[0]],
            nat_gateways=1
        )
        return vpc

    def get_image_to_task_container(self, task_def, repo_name, tag_name, container_name, log_group_name):
        ecr_repo = ecr.Repository(
            self, repo_name
        )
        container = task_def.add_container(
            container_name,
            image=ecs.ContainerImage.from_ecr_repository(ecr_repo, tag_name),
            memory_limit_mib=512,
            logging=ecs.AwsLogDriver(
                stream_prefix=container_name,
                log_group=logs.LogGroup(self, log_group_name,
                                        log_group_name=log_group_name,
                                        removal_policy=core.RemovalPolicy.DESTROY)
            )
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port=80)
        )
        return task_def

    def create_fargate_SG(self):
        sg = ec2.SecurityGroup(self, id="fargateSG", vpc=self.vpc, allow_all_outbound=False, description="fargate service Security Group")
        sg.add_ingress_rule(peer=ec2.Peer.ipv4(VPC_CIDR), connection=ec2.Port.tcp(80), description="HTTP ingress")
        sg.add_ingress_rule(peer=ec2.Peer.ipv4(VPC_CIDR), connection=ec2.Port.tcp(443), description="HTTPS ingress")
        sg.add_egress_rule(peer=ec2.Peer.ipv4("0.0.0.0/0"), connection=ec2.Port.tcp(80), description="HTTP egress")
        sg.add_egress_rule(peer=ec2.Peer.ipv4("0.0.0.0/0"), connection=ec2.Port.tcp(443), description="HTTPS egress")
        return sg

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

        # 将 Lambda 函数的执行角色授权给 Amazon Aurora 数据库
        # cluster.grant_data_api_access(
        #     db_name=database_name,
        #     grantee=aurora_lambda.role
        # )

        # 添加 Lambda 执行角色的 IAM 权限，以允许访问 Secrets Manager 中的数据库凭据
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
            engine=rds.DatabaseClusterEngine.aurora(
                version=rds.AuroraEngineVersion.VER_1_19_0
            ),
            instance_props={
                "instance_type": ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE2, ec2.InstanceSize.SMALL),
                "vpc_subnets": {
                    "subnet_type": ec2.SubnetType.PRIVATE_WITH_EGRESS
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