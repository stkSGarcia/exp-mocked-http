## ADDED Requirements

### Requirement: Hot reload enabled via environment variable
The server SHALL read `HM_TEMPLATES_DIR_HOT_RELOAD` at startup. When the value is `true` (default), the server SHALL watch `HM_TEMPLATES_DIR` for filesystem changes and reload the template collection automatically. When the value is `false`, templates SHALL only be loaded at startup or at admin API reload boundaries.

#### Scenario: Default value enables hot reload
- **WHEN** the server starts with no `HM_TEMPLATES_DIR_HOT_RELOAD` set
- **THEN** hot reload is active and filesystem changes are picked up automatically

#### Scenario: Explicit false disables hot reload
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD=false`
- **THEN** filesystem edits to the templates directory do not affect request handling until restart or admin reload

### Requirement: New template file becomes visible after hot reload
When hot reload is enabled and a new YAML file is created under `HM_TEMPLATES_DIR`, the server SHALL begin matching requests against the new behaviors within the reload window without restarting.

#### Scenario: New file picked up
- **WHEN** a new `.yaml` file is added to `HM_TEMPLATES_DIR` while the server is running
- **THEN** the behaviors defined in that file become matchable within the reload interval

### Requirement: Edited template file reflected after hot reload
When hot reload is enabled and an existing YAML file under `HM_TEMPLATES_DIR` is modified, the server SHALL use the updated behavior definitions for subsequent requests.

#### Scenario: Edited file reflected
- **WHEN** an existing `.yaml` template file is modified on disk
- **THEN** subsequent requests use the updated behavior definition

### Requirement: Deleted template file removed after hot reload
When hot reload is enabled and a YAML file is deleted from `HM_TEMPLATES_DIR`, the behaviors it defined SHALL no longer be available for matching.

#### Scenario: Deleted file removed
- **WHEN** a `.yaml` template file is deleted from `HM_TEMPLATES_DIR`
- **THEN** requests that previously matched behaviors in that file return 404

### Requirement: Hot reload is atomic
Template state SHALL be replaced atomically. A request arriving during a reload cycle SHALL see either the old complete template set or the new complete template set, never a partial state.

#### Scenario: Partial state not observed
- **WHEN** a reload is in progress and a request arrives
- **THEN** the request is handled with a fully consistent template set (old or new, not mixed)

### Requirement: Reload failure preserves previous state
When a hot reload cycle encounters a validation error in the updated template files, the server SHALL retain the previously loaded template set and log an error. The server SHALL NOT crash or enter an inconsistent state.

#### Scenario: Invalid YAML leaves previous templates intact
- **WHEN** a template file is edited to contain invalid YAML and hot reload triggers
- **THEN** the server logs an error and continues serving requests using the previous valid template set

### Requirement: Startup log indicates reload mode
The server SHALL log at startup whether hot reload is active and which mechanism (filesystem watch or polling) is in use.

#### Scenario: Startup log message emitted
- **WHEN** the server starts with hot reload enabled
- **THEN** a log entry at info level states that hot reload is active
