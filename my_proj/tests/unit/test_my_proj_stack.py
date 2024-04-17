import aws_cdk as core
import aws_cdk.assertions as assertions

from my_proj.my_proj_stack import MyProjStack

# example tests. To run these tests, uncomment this file along with the example
# resource in my_proj/my_proj_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = MyProjStack(app, "my-proj")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
