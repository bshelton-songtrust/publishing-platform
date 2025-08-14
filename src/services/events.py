"""Event publishing service for catalog changes."""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum

import boto3
from botocore.exceptions import ClientError

from src.core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EventType(Enum):
    """Catalog event types."""
    WORK_CREATED = "catalog.work.created"
    WORK_UPDATED = "catalog.work.updated"
    WORK_DELETED = "catalog.work.deleted"
    SONGWRITER_CREATED = "catalog.songwriter.created"
    SONGWRITER_UPDATED = "catalog.songwriter.updated"
    SONGWRITER_DELETED = "catalog.songwriter.deleted"
    RECORDING_CREATED = "catalog.recording.created"
    RECORDING_UPDATED = "catalog.recording.updated"
    RECORDING_DELETED = "catalog.recording.deleted"
    WORK_WRITER_ADDED = "catalog.work_writer.added"
    WORK_WRITER_REMOVED = "catalog.work_writer.removed"
    WORK_WRITER_UPDATED = "catalog.work_writer.updated"


@dataclass
class CatalogEvent:
    """Base catalog event structure."""
    event_type: EventType
    tenant_id: str
    user_id: str
    resource_id: str
    resource_type: str
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    
    # Auto-generated fields
    event_id: str = None
    timestamp: str = None
    version: str = "1.0"
    
    def __post_init__(self):
        if self.event_id is None:
            self.event_id = str(uuid.uuid4())
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


class EventPublisher:
    """Service for publishing catalog events."""
    
    def __init__(self):
        self.event_bus_type = settings.event_bus_type
        self.sqs_client = None
        self.queue_url = settings.sqs_event_queue_url
        
        if self.event_bus_type == "sqs":
            self._initialize_sqs()
    
    def _initialize_sqs(self):
        """Initialize SQS client."""
        try:
            self.sqs_client = boto3.client(
                "sqs",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
            logger.info("SQS client initialized for event publishing")
        except Exception as e:
            logger.error(f"Failed to initialize SQS client: {e}")
            self.sqs_client = None
    
    async def publish_event(self, event: CatalogEvent) -> bool:
        """Publish a catalog event."""
        try:
            if self.event_bus_type == "sqs":
                return await self._publish_to_sqs(event)
            else:
                # Mock mode for development
                return await self._publish_mock(event)
        except Exception as e:
            logger.error(f"Failed to publish event {event.event_id}: {e}")
            return False
    
    async def _publish_to_sqs(self, event: CatalogEvent) -> bool:
        """Publish event to SQS queue."""
        if not self.sqs_client or not self.queue_url:
            logger.warning("SQS not properly configured, skipping event publish")
            return False
        
        try:
            message_body = json.dumps(asdict(event), default=str)
            message_attributes = {
                "event_type": {
                    "StringValue": event.event_type.value,
                    "DataType": "String"
                },
                "tenant_id": {
                    "StringValue": event.tenant_id,
                    "DataType": "String"
                },
                "resource_type": {
                    "StringValue": event.resource_type,
                    "DataType": "String"
                }
            }
            
            response = self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=message_body,
                MessageAttributes=message_attributes,
                MessageGroupId=event.tenant_id,  # For FIFO queues
                MessageDeduplicationId=event.event_id
            )
            
            logger.info(f"Published event {event.event_id} to SQS: {response['MessageId']}")
            return True
            
        except ClientError as e:
            logger.error(f"SQS error publishing event {event.event_id}: {e}")
            return False
    
    async def _publish_mock(self, event: CatalogEvent) -> bool:
        """Mock event publishing for development."""
        logger.info(f"MOCK EVENT: {event.event_type.value} - {event.event_id}")
        logger.debug(f"Event data: {json.dumps(asdict(event), indent=2, default=str)}")
        return True
    
    async def publish_work_created(
        self, 
        work_id: str, 
        work_data: Dict[str, Any],
        tenant_id: str,
        user_id: str
    ) -> bool:
        """Publish work created event."""
        event = CatalogEvent(
            event_type=EventType.WORK_CREATED,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id=work_id,
            resource_type="work",
            data=work_data,
            metadata={
                "source": "catalog_management_service",
                "api_version": "v1"
            }
        )
        return await self.publish_event(event)
    
    async def publish_work_updated(
        self,
        work_id: str,
        work_data: Dict[str, Any],
        changes: Dict[str, Any],
        tenant_id: str,
        user_id: str
    ) -> bool:
        """Publish work updated event."""
        event = CatalogEvent(
            event_type=EventType.WORK_UPDATED,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id=work_id,
            resource_type="work",
            data=work_data,
            metadata={
                "source": "catalog_management_service",
                "api_version": "v1",
                "changes": changes
            }
        )
        return await self.publish_event(event)
    
    async def publish_work_deleted(
        self,
        work_id: str,
        tenant_id: str,
        user_id: str
    ) -> bool:
        """Publish work deleted event."""
        event = CatalogEvent(
            event_type=EventType.WORK_DELETED,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id=work_id,
            resource_type="work",
            data={"deleted": True},
            metadata={
                "source": "catalog_management_service",
                "api_version": "v1"
            }
        )
        return await self.publish_event(event)
    
    async def publish_songwriter_created(
        self,
        songwriter_id: str,
        songwriter_data: Dict[str, Any],
        tenant_id: str,
        user_id: str
    ) -> bool:
        """Publish songwriter created event."""
        event = CatalogEvent(
            event_type=EventType.SONGWRITER_CREATED,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id=songwriter_id,
            resource_type="songwriter",
            data=songwriter_data,
            metadata={
                "source": "catalog_management_service",
                "api_version": "v1"
            }
        )
        return await self.publish_event(event)
    
    async def publish_songwriter_updated(
        self,
        songwriter_id: str,
        songwriter_data: Dict[str, Any],
        changes: Dict[str, Any],
        tenant_id: str,
        user_id: str
    ) -> bool:
        """Publish songwriter updated event."""
        event = CatalogEvent(
            event_type=EventType.SONGWRITER_UPDATED,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id=songwriter_id,
            resource_type="songwriter",
            data=songwriter_data,
            metadata={
                "source": "catalog_management_service",
                "api_version": "v1",
                "changes": changes
            }
        )
        return await self.publish_event(event)
    
    async def publish_recording_created(
        self,
        recording_id: str,
        recording_data: Dict[str, Any],
        tenant_id: str,
        user_id: str
    ) -> bool:
        """Publish recording created event."""
        event = CatalogEvent(
            event_type=EventType.RECORDING_CREATED,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id=recording_id,
            resource_type="recording",
            data=recording_data,
            metadata={
                "source": "catalog_management_service",
                "api_version": "v1"
            }
        )
        return await self.publish_event(event)
    
    async def publish_recording_updated(
        self,
        recording_id: str,
        recording_data: Dict[str, Any],
        changes: Dict[str, Any],
        tenant_id: str,
        user_id: str
    ) -> bool:
        """Publish recording updated event."""
        event = CatalogEvent(
            event_type=EventType.RECORDING_UPDATED,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id=recording_id,
            resource_type="recording",
            data=recording_data,
            metadata={
                "source": "catalog_management_service",
                "api_version": "v1",
                "changes": changes
            }
        )
        return await self.publish_event(event)
    
    async def publish_work_writer_added(
        self,
        work_id: str,
        songwriter_id: str,
        writer_data: Dict[str, Any],
        tenant_id: str,
        user_id: str
    ) -> bool:
        """Publish work writer added event."""
        event = CatalogEvent(
            event_type=EventType.WORK_WRITER_ADDED,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id=work_id,
            resource_type="work_writer",
            data={
                "work_id": work_id,
                "songwriter_id": songwriter_id,
                **writer_data
            },
            metadata={
                "source": "catalog_management_service",
                "api_version": "v1"
            }
        )
        return await self.publish_event(event)


# Global event publisher instance
_event_publisher = None


def get_event_publisher() -> EventPublisher:
    """Get the global event publisher instance."""
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisher()
    return _event_publisher


class EventBatch:
    """Helper for publishing multiple events as a batch."""
    
    def __init__(self, publisher: EventPublisher):
        self.publisher = publisher
        self.events: List[CatalogEvent] = []
    
    def add_event(self, event: CatalogEvent):
        """Add event to batch."""
        self.events.append(event)
    
    async def publish_all(self) -> Dict[str, bool]:
        """Publish all events in batch."""
        results = {}
        for event in self.events:
            success = await self.publisher.publish_event(event)
            results[event.event_id] = success
        return results
    
    def clear(self):
        """Clear all events from batch."""
        self.events.clear()