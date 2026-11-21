@e2e
Feature: Tickets from the built binary
  These scenarios never reach a real ticket system. They cover what only the
  packaged zipapp can prove: that the built-in providers are inside it, that a
  provider plugin on disk is discovered by it, that guards fire before any
  network call, and that data and chatter land on the right streams.

  Scenario: With no sources configured, grind says how to add one
    Given no config file exists
    When I run the CLI with no arguments
    Then the exit code is 1
    And stdout is empty
    And stderr contains "No sources configured"
    And stderr contains "config init"

  Scenario: The built-in providers are packaged in the binary
    Given a config file with GitHub and JIRA sources
    When I run the CLI with `--no-colour sources`
    Then the exit code is 0
    And stdout contains "github"
    And stdout contains "jira"
    And stdout contains "built-in"
    And stdout contains "https://jira.invalid"

  Scenario: An ambiguous reference is refused before any network call
    Given a config file with GitHub and JIRA sources
    When I run the CLI with `--no-colour show PROJ-1`
    Then the exit code is 1
    And stdout is empty
    And stderr contains "<source>:<key>"

  Scenario: The plugin directory lives under the XDG data home
    When I run the CLI with `sources --plugin-dir`
    Then the exit code is 0
    And stdout names the plugin directory in the sandbox

  Scenario: A provider plugin on disk is discovered by the binary
    Given a provider plugin named "decaf" is installed
    And a config file with a "decaf" source
    When I run the CLI with `--no-colour sources`
    Then the exit code is 0
    And stdout contains "decaf"
    And stdout contains "plugin (grind_decaf:DecafProvider)"

  Scenario: Tickets go to stdout and progress goes to stderr
    Given a provider plugin named "decaf" is installed
    And a config file with a "decaf" source
    When I run the CLI with `--no-colour list`
    Then the exit code is 0
    And stdout contains "pot:DECAF-1"
    And stdout contains "Refill the decaf jar"
    And stdout does not contain "Grinding"
    And stderr contains "Grinding through your tickets"
    And stdout carries no ANSI colour

  Scenario: JSON output is nothing but JSON
    Given a provider plugin named "decaf" is installed
    And a config file with a "decaf" source
    When I run the CLI with `list --format json`
    Then the exit code is 0
    And stdout is valid JSON
    And the JSON lists the ticket "pot:DECAF-1"

  Scenario: A write the provider cannot do is a clean error
    Given a provider plugin named "decaf" is installed
    And a config file with a "decaf" source
    When I run the CLI with `--no-colour comment pot:DECAF-1 hello`
    Then the exit code is 1
    And stdout is empty
    And stderr contains "does not support commenting"

  Scenario: A cached list survives into the next process
    Given a provider plugin named "decaf" is installed
    And a config file with a "decaf" source
    When I run the CLI with `--no-colour --cache list`
    And I run the CLI with `--no-colour --cache --debug-summary list`
    Then the exit code is 0
    And stdout contains "pot:DECAF-1"
    And stderr contains "Requests to pot: 0"
