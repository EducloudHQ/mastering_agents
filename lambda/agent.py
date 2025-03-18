import os
from http.client import HTTPException

import boto3

from botocore.exceptions import ClientError

from typing_extensions import Annotated
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.event_handler import BedrockAgentResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.data_classes.appsync import scalar_types_utils
from aws_lambda_powertools.event_handler.openapi.params import Body, Query, Path

tracer = Tracer()
logger = Logger()

app = BedrockAgentResolver()
dynamodb = boto3.resource("dynamodb")

table_name = os.environ.get("TODO_TABLE")
knowledge_base_id = os.environ.get("KNOWLEDGE_BASE_ID")

table = dynamodb.Table(table_name)

metrics = Metrics(namespace="todo_app_metrics")
bedrock = boto3.client('bedrock-runtime', 'us-east-1')
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime','us-east-1')

@app.post("/create_todo",
          description="Creates a todo item in dynamodb by passing todo id,"
                      " todo name and todo description and status")
@tracer.capture_method
def create_todo(
        title: Annotated[str, Query(description="title of the todo")],
        description: Annotated[str, Query(description="todo description")],
) -> Annotated[bool, Body(description="Whether the todo was created successfully")]:
    todo_id = scalar_types_utils.make_id()
    try:
        response = table.put_item(
            Item={
                'id': todo_id,
                'title': title,
                'description': description,
                'status': 'pending'
            }
        )
        logger.info(f"Created todo id: {todo_id}")

        return True
    except ClientError as e:
        logger.error(f"Error creating todo:, ${e.response['Error']['Message']}")
        return False


@app.get("/list_todos",
         description="list all todos in the dynamodb table")
@tracer.capture_method
def list_todos() -> Annotated[list, Body(description="A list of todos from the dyanmodb table")]:
    try:
        response = table.scan()
        items = response.get('Items', [])
        print("Listing ToDo Items:")
        for item in items:
            logger.info(f" todos ${item}")
        return items
    except ClientError as e:
        print("Error listing items:", e.response['Error']['Message'])
        return []


@app.put("/update_todo",
         description="Update a todo in dynamodb table based on its todo id,title,description and status ")
@tracer.capture_method
def update_todo(
        todo_id: Annotated[str, Query(description="Id of todo item to be updated")],
        title: Annotated[str, Query(description="title of todo")],
        description: Annotated[str, Query(description="Description of todo")],
        status: Annotated[str, Query(description="Status of tod")]
) -> Annotated[bool, Body(description="Whether todo was updated successfully")]:
    # Build the update expression and attribute values dynamically
    update_expression = []
    expression_attribute_values = {}
    expression_attribute_names = {}

    if title is not None:
        update_expression.append("title = :t")
        expression_attribute_values[":t"] = title
    if description is not None:
        update_expression.append("description = :d")
        expression_attribute_values[":d"] = description
    if status is not None:
        # Alias the reserved keyword "status" using a placeholder (#s)
        update_expression.append("#s = :s")
        expression_attribute_values[":s"] = status
        expression_attribute_names["#s"] = "status"

    if not update_expression:
        logger.info("No attributes provided to update.")
        return False

    update_expr = "SET " + ", ".join(update_expression)

    try:
        response = table.update_item(
            Key={'id': todo_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ReturnValues="UPDATED_NEW"
        )
        logger.info(f"Todo item '{todo_id}' updated successfully.")
        return True
    except ClientError as e:
        print("Error updating item:", e.response['Error']['Message'])
        return False




@app.delete("/delete_todo",
         description="delete a todo item in dynamodb table based on its id")
@tracer.capture_method
def delete_todo(
        todo_id: Annotated[str,Query(description="Id of todo item to be updated")],
) -> Annotated[bool, Body(description="Whether todo was deleted successfully")]:
    try:
        response = table.delete_item(
            Key={'id': todo_id}
        )
        logger.info(f"Todo item '{todo_id}' deleted successfully.")
        return True
    except ClientError as e:
        logger.error("Error deleting item:", e.response['Error']['Message'])
        return False


@app.get("/get_todo",
         description="get a todo in dynamodb table based on its id")
@tracer.capture_method
def get_todo(
        todo_id: Annotated[str, Query(description="Id of todo item to be updated")],
) -> Annotated[str, Body(description="retrieve a todo")]:
    try:
        response = table.get_item(
            Key={'id': todo_id}
        )
        item = response.get('Item')
        if item:
            logger.info(f"Retrieved item: {item}")
        else:
            logger.info(f"No item found with id '{todo_id}'.")
        return f"todo item is ${item}"
    except ClientError as e:
        logger.info("Error retrieving item:", e.response['Error']['Message'])
        return None


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext):
    return app.resolve(event, context)


if __name__ == "__main__":
    print(app.get_openapi_json_schema())
