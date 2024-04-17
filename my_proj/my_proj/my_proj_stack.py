import os.path

from aws_cdk import (
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    CfnOutput,
    Stack
)
from aws_cdk.aws_autoscaling import AutoScalingGroup
from constructs import Construct

VPC_CIDR = "172.32.0.0/16"
SUBNET_SIZE = 26
SUBNET_CIDRS = ['172.32.1.0/24', '172.32.2.0/24']
AV_ZONES = ['ap-southeast-2a', 'ap-southeast-2b']
class MyProjStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 创建 VPC
        self.vpc = self.create_VPC()

        self.instance_lst = []
        nat_instance = self.create_nat_instance()
        self.add_route_to_nat(nat_instance)
        for i in range(2):
            self.instance_lst.append(self.create_ec2_instance("MyInstance" + str(i + 1), ec2.SubnetType.PUBLIC))
        alb = self.create_ALB_in_lz()


    def create_ec2_instance(self, instance_name, subnet_type):
        # 创建 EC2 实例
        ec2_instance = ec2.Instance(self, instance_name,
                                    instance_type=ec2.InstanceType.of(
                                        ec2.InstanceClass.BURSTABLE2,
                                        ec2.InstanceSize.MICRO),
                                    machine_image=ec2.AmazonLinuxImage(),
                                    vpc=self.vpc,
                                    vpc_subnets=ec2.SubnetSelection(
                                        availability_zones=[AV_ZONES[0]],
                                        subnet_type=subnet_type),
                                    )
        # 启动 httpd 服务
        ec2_instance.add_user_data("sudo yum install -y httpd", "sudo systemctl start httpd")
        self.instance_lst.append(ec2_instance)
        return ec2_instance

        # 创建负载均衡器
        # load_balancer = elbv2.ApplicationLoadBalancer(self, "MyLoadBalancer",
        #     vpc=self.vpc,
        #     internet_facing=True,
        #     load_balancer_name="my-load-balancer"
        # )

        # data = open("my_proj/httpd.sh", "rb").read()
        # httpd = ec2.UserData.for_linux()
        # httpd.add_commands(str(data, 'utf-8'))
        # asg = AutoScalingGroup(
        #     self,
        #     "ASG",
        #     vpc=self.vpc,
        #     instance_type=ec2.InstanceType.of(
        #         ec2.InstanceClass.BURSTABLE2, ec2.InstanceSize.MICRO
        #     ),
        #     machine_image=ec2.AmazonLinuxImage(generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2),
        #     # user_data=httpd,
        # )

        # 添加 Listener，并将 Target Group1 和 Target Group2 关联
        # listener = load_balancer.add_listener("MyListener", port=80)
        # listener.add_targets("Target", port=80, targets=[asg])
        # listener.connections.allow_default_port_from_any_ipv4("Open to the world")
        #
        # asg.scale_on_request_count("AModestLoad", target_requests_per_minute=60)
        # # for i in range(len(instance_lst)):
        # #     listener.add_targets("MyTargetGroup" + str(i+1), port=80, targets=[instance_lst[i]])
        #
        # # 输出负载均衡器的 DNS 名称
        # CfnOutput(self, "LoadBalancerDNS",
        #     value=load_balancer.load_balancer_dns_name
        # )

    def get_user_data(self, filename):
        with open(os.path.join(os.getcwd(), "user_data\\") + filename) as f:
            user_data = f.read()
        return user_data

    def create_VPC(self):
        vpc = ec2.Vpc(
            self,
            "Vpc",
            ip_addresses = ec2.IpAddresses.cidr(VPC_CIDR),
            subnet_configuration = [
                ec2.SubnetConfiguration(
                    name = 'Public-Subnet',
                    subnet_type = ec2.SubnetType.PUBLIC,
                    cidr_mask = SUBNET_SIZE,

                ),
                ec2.SubnetConfiguration(
                    name = 'Private-Subnet',
                    subnet_type = ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask = SUBNET_SIZE,
                ),
            ],
            availability_zones = [AV_ZONES[0]]
        )
        return vpc

    def create_nat_instance(self):
        amzn_linux = ec2.MachineImage.latest_amazon_linux(
            generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2)
        user_data = self.get_user_data("nat_instance")
        nat = ec2.Instance(self, "NATInstanceInLZ",
                 vpc=self.vpc,
                 security_group=self.create_nat_SG(),
                 instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
                 machine_image=amzn_linux,
                 user_data=ec2.UserData.custom(user_data),
                 vpc_subnets=ec2.SubnetSelection(
                     availability_zones=[AV_ZONES[0]],
                     subnet_type=ec2.SubnetType.PUBLIC),
                 source_dest_check=False
                )
        return nat

    # method to add a default route in the private subnet pointing to the NAT instance
    def add_route_to_nat(self, nat_instance):
        # select the private subnet created before
        priv_subnets = self.vpc.select_subnets(
            availability_zones = [AV_ZONES[0]],
            subnet_type  = ec2.SubnetType.PRIVATE_ISOLATED
        )
        # add the default route pointing to the nat instance
        priv_subnets.subnets[0].add_route("DefRouteToNAT",
                              router_id=nat_instance.instance_id,
                              router_type=ec2.RouterType.INSTANCE,
                              destination_cidr_block="0.0.0.0/0",
                              enables_internet_connectivity=True)

    # method to add the Security Group attached to the NAT instance
    def create_nat_SG(self):
        sg = ec2.SecurityGroup(self, id="NatInstanceSG", vpc=self.vpc, allow_all_outbound=False, description="Nat Instance Security Group")
        sg.add_ingress_rule(peer=ec2.Peer.ipv4(VPC_CIDR), connection=ec2.Port.tcp(80), description="HTTP ingress")
        sg.add_ingress_rule(peer=ec2.Peer.ipv4(VPC_CIDR), connection=ec2.Port.tcp(443), description="HTTPS ingress")
        sg.add_egress_rule(peer=ec2.Peer.ipv4("0.0.0.0/0"), connection=ec2.Port.tcp(80), description="HTTP egress")
        sg.add_egress_rule(peer=ec2.Peer.ipv4("0.0.0.0/0"), connection=ec2.Port.tcp(443), description="HTTPS egress")
        return sg

    def create_ALB_in_lz(self):
        alb = elbv2.ApplicationLoadBalancer(self,
                                            "ALB_in_LZ",
                                            vpc=self.vpc,
                                            internet_facing=True,
                                            vpc_subnets=ec2.SubnetSelection(availability_zones=[AV_ZONES[0]],subnet_type=ec2.SubnetType.PUBLIC)
                                            )
        http_listener = alb.add_listener("ListenerHTTP", port=80)
        for i in range(len(self.instance_lst)):
            target_group = elbv2.ApplicationTargetGroup(self,
                                                        "MyTargetGroup" + str(i + 1),
                                                        vpc=self.vpc,
                                                        port=80,
                                                        # targets=[self.instance_lst[i]],
                                                        target_group_name="myTargetGroup" + str(i + 1))
            target_group.add_target(self.instance_lst[i])
            http_listener.add_target_groups(target_group)
            target_group.configure_health_check(
                healthy_http_codes="200,301"
            )
            # tg = http_listener.add_targets("AppFleet", port=80,target_groups=[target_group])
            # tg.configure_health_check(
            #     healthy_http_codes = "200,301"
            # )
        http_listener.connections.allow_default_port_from_any_ipv4("ALB access on target instance")
        return alb
