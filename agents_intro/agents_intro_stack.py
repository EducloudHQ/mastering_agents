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
    AgentCollaborator,
    AgentCollaboratorType,
    RelayConversationHistoryType,
    BedrockFoundationModel,
    AgentActionGroup,
    ActionGroupExecutor,
    AgentAlias,
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

        todo_agent = Agent(
            self,
            "Agent",

            foundation_model=BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
            instruction="You are a helpful and friendly agent that performs CRUDL operations on a dynamodb table",
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


        todo_agent_alias = AgentAlias(
            self,
            "AgentAlias",
            agent=todo_agent,
            alias_name="todo_agent_alias",
            description="Todo Alias for description"
        )
        customer_support_agent = Agent(
            self,
            "CustomerSupportAgent",

            foundation_model=BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
            instruction="You Specialize in answering customer support questions for our workshops",
        )

        support_agent_alias = AgentAlias(
            self,
            "CustomerSupportAgentAlias",
            agent=customer_support_agent,
            alias_name="customer_support_agent_alias",
            description="Customer Support Agent Alias for description"
        )

        content_generation_agent = Agent(
            self,
            "ContentGenerationAgent",

            foundation_model=BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
            instruction="You Specialize in answering content generation questions for our workshops",
        )

        content_generation_agent_alias = AgentAlias(
            self,
            "ContentGenerationAgentAlias",
            agent=content_generation_agent,
            alias_name="content_generation_agent_alias",
            description="Content Generation Agent Alias for description"
        )

        supervisor_agent = Agent(
            self,
            "SuperVisorAgent",
            foundation_model=BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
            instruction=(
                "You are a helpful and friendly supervisor agent that routes user queries to the appropriate specialized agents. "
                "Analyze the user's request carefully and determine the most suitable agent based on the following roles: "
                "(1) Route questions regarding todo item management (create, read, update, delete, list tasks) to the TodoAgent. "
                "(2) Route customer support related questions, such as troubleshooting or workshop inquiries, to the CustomerSupportAgent. "
                "(3) Route content generation requests like creating summaries, workshop flashcards, or general content-related questions to the ContentGenerationAgent. "
                "If the user's query doesn't fit into any specialized category, you may provide general assistance directly."
            ),
            agent_collaboration=AgentCollaboratorType.SUPERVISOR,
            agent_collaborators=[
                AgentCollaborator(
                    agent_alias=todo_agent_alias,
                    collaborator_name="TodoAgent",
                    collaboration_instruction="Route Todo questions to this agent",
                    relay_conversation_history=True

                ),
                AgentCollaborator(
                    agent_alias=support_agent_alias,
                    collaborator_name="CustomerSupportAgent",
                    collaboration_instruction="Route Customer support(FAQ) questions to this agent",
                    relay_conversation_history=True

                ),
                AgentCollaborator(
                    agent_alias=content_generation_agent_alias,
                    collaborator_name="WorkshopContentGenerationAgent",
                    collaboration_instruction="Route all workshop content generation questions to this agent",
                    relay_conversation_history=True

                ),
            ]

        )


        todo_agent.add_action_group(action_group)
        pinecone_vec = PineconeVectorStore(
            connection_string='https://ai-fddfghggklkjnlknjmvjhvbhjbvjhvbjvhfghbnvbjhv.io',
            credentials_secret_arn='arn:aws:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxaToyuv',
            text_field='text',
            metadata_field='metadata'
        )

        kb = VectorKnowledgeBase(self, 'KnowledgeBaseAgent',
                                 vector_store=pinecone_vec,
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

        content_generation_agent.add_knowledge_base(knowledge_base=kb)
        kb.grant_retrieve_and_generate(action_group_function)
        action_group_function.add_environment("KNOWLEDGE_BASE_ID",kb.knowledge_base_id)
