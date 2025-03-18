import aws_cdk
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from cdklabs.generative_ai_cdk_constructs.pinecone import PineconeVectorStore
from constructs import Construct

from aws_cdk import Stack, Duration, aws_s3
from aws_cdk.aws_dynamodb import Table, Attribute, AttributeType, BillingMode
from aws_cdk.aws_lambda import Runtime, Tracing
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from aws_cdk.aws_secretsmanager import Secret
from constructs import Construct
from cdklabs.generative_ai_cdk_constructs.bedrock import (
    Agent,
    BedrockFoundationModel,
    AgentActionGroup,
    ActionGroupExecutor,
    KnowledgeBaseType,
    KnowledgeBaseBase,

    Guardrail,
    Topic,
    ApiSchema, VectorKnowledgeBase, S3DataSource, ChunkingStrategy,
)


class AgentsIntroStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define the DynamoDB table
        todo_table = Table(
            self,
            "TodoAgentTable",
            table_name="TodoAgentTable",
            partition_key=Attribute(
                name="id", type=AttributeType.STRING
            ),

            billing_mode=BillingMode.PAY_PER_REQUEST,

        )

        action_group_function = PythonFunction(
            self,
            "TodoAgentLambdaFunction",
            runtime=Runtime.PYTHON_3_11,
            entry="./lambda",
            index="agent.py",
            handler="lambda_handler",
        )

        todo_table.grant_full_access(action_group_function)
        action_group_function.add_environment("TODO_TABLE", todo_table.table_name)

        agent = Agent(
            self,
            "Agent",

            foundation_model=BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
            instruction="You are a helpful and friendly agent that perfroms multiple actions on a dynamodb table",
        )

        action_group: AgentActionGroup = AgentActionGroup(
            name="TodoApiSupport",
            description="Use these functions to create/update/delete and list todo items",
            executor=ActionGroupExecutor.fromlambda_function(
                lambda_function=action_group_function,
            ),
            enabled=True,
            api_schema=ApiSchema.from_local_asset("./lambda/openapi.json"),
        )

        agent.add_alias(
            alias_name="todo_agent_alias", description="Alias for description"
        )

        agent.add_action_group(action_group)
        pineconevs = PineconeVectorStore(
            connection_string='https://ai-learning-app-kb-pbfqwcb.svc.aped-4627-b74a.pinecone.io',
            credentials_secret_arn='arn:aws:secretsmanager:us-east-1:132260253285:secret:bedrock-pinecone-apikey-aToyuv',
            text_field='text',
            metadata_field='metadata'
        )

        kb = VectorKnowledgeBase(self, 'KnowledgeBaseAgent',
                                 vector_store=pineconevs,
                                 embeddings_model=BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024,
                                 instruction='Use this knowledge base to summarize,generate QA and flash cards about workshops ' +
                                             'It contains some workshops gotten from educloud academy.'
                                 )

        docBucket = aws_s3.Bucket(
            self,
            "ai-learning-bucket",
            versioned=False,
            encryption=aws_s3.BucketEncryption.S3_MANAGED,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
        )

        S3DataSource(self, 'DataSource',
                     bucket=docBucket,
                     knowledge_base=kb,
                     data_source_name='ai-todo-workshops',
                     chunking_strategy=ChunkingStrategy.FIXED_SIZE,
                     )

        agent.add_knowledge_base(knowledge_base=kb)
        kb.grant_retrieve_and_generate(action_group_function)
        action_group_function.add_environment("KNOWLEDGE_BASE_ID",kb.knowledge_base_id)
