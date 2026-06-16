## ADDED Requirements

> Extends: http-behavior-mocking

### Requirement: Broker Publish Action Ordering
The system SHALL execute `publish_kafka` and `publish_amqp` actions using the same stable ascending `order` semantics as other behavior actions.

#### Scenario: Broker publish actions are sorted by ascending order
- **GIVEN** a selected behavior contains broker publish actions and other actions with different `order` values
- **WHEN** the behavior executes
- **THEN** the system SHALL execute lower order values before higher order values

#### Scenario: Broker publish actions preserve declared order for ties
- **GIVEN** a selected behavior contains `publish_kafka`, `publish_amqp`, and other actions with the same effective `order`
- **WHEN** the behavior executes
- **THEN** the system SHALL execute those actions in the order declared by the effective behavior

#### Scenario: Missing broker publish order defaults to zero
- **GIVEN** a selected behavior contains a broker publish action without `order`
- **WHEN** the behavior executes
- **THEN** the system SHALL treat that action's order as `0`
