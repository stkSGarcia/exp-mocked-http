## ADDED Requirements

> Extends: kafka-message-handling/add-kafka-amqp-message-handling

### Requirement: AMQP Evaluation Queue Fallback
The system SHALL evaluate `mock.expect.amqp.queue` as the AMQP routing key when `queue` is omitted or empty in an evaluation request.

#### Scenario: Missing AMQP queue uses routing key
- **GIVEN** a mock expectation declares `expect.amqp.exchange` and `expect.amqp.routing_key`
- **AND** `expect.amqp.queue` is omitted
- **WHEN** the mock is evaluated against matching `context.amqp_context`
- **THEN** the evaluator treats the expected queue as the routing key

#### Scenario: Empty AMQP queue uses routing key
- **GIVEN** a mock expectation declares `expect.amqp.queue` as an empty string
- **WHEN** the mock is evaluated against matching `context.amqp_context`
- **THEN** the evaluator treats the expected queue as the routing key
