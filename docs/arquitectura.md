Viernes Architecture

Viernes is designed as a modular local AI system rather than as a single program that is expected to perform every task by itself.

The main idea is to keep the language model relatively small and surround it with specialized components that handle tasks the model does not need to perform directly.

General architecture

                         USER
                           │
                           ▼
                    ┌─────────────┐
                    │ CONTROLLER  │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   VIERNES   │
                    │  Local LLM  │
                    └──────┬──────┘
                           │
                       result
                           │
                           ▼
                    ┌─────────────┐
                    │   REVIEWER  │
                    └──────┬──────┘
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
             VERIFIED            REVIEW

Several supporting components operate around this core:

                  ┌─────────────────────┐
                  │    INFORMATION BOTS  │
                  └──────────┬──────────┘
                             │
                             ▼
USER → CONTROLLER → VIERNES → REVIEWER
                       │          │
                       │          ▼
                       │      DATABASE
                       │
                       ▼
                  OTHER TOOLS


                  WATCHDOG
                     │
                     ▼
              Process health
              and recovery

Main components

Viernes

Viernes is the user-facing local AI and reasoning component.

It uses a local language model to:

- understand requests;
- reason about available information;
- interact with the user;
- coordinate work through the surrounding system;
- interpret information collected by specialized components;
- produce responses and results.

The intention is not for the model to perform every mechanical operation itself.

Instead, Viernes should increasingly rely on specialized tools and bots when a task can be performed more efficiently outside the language model.

---

Controller

The Controller manages the lifecycle of tasks.

Its responsibilities include:

- receiving tasks;
- assigning their state;
- starting and tracking processing;
- receiving results;
- storing relevant information;
- recovering unfinished work after a restart;
- sending results to the appropriate verification stage.

The intended task lifecycle is:

INBOX
  │
  ▼
PROCESSING
  │
  ├──────────────► VERIFIED
  │
  └──────────────► REVIEW

The Controller is intentionally separate from the watchdog.

The Controller deals with tasks and their state.

The Watchdog deals with process health.

---

Reviewer

The Reviewer evaluates the results produced by Viernes.

It is intended to prevent incorrect or unverified information from being treated as reliable data.

A result may therefore be classified as:

- verified;
- requiring review;
- incorrect;
- discarded.

The original model output should be preserved when appropriate, including incorrect outputs. Errors can provide useful information for understanding model limitations and, in the future, for creating controlled evaluation or training datasets.

The Reviewer should not simply trust the model when it claims that an answer is correct. Verification should be based on defined criteria and available evidence.

---

Information Bots

Information bots are specialized components designed to collect, transform or prepare information for Viernes.

A bot does not necessarily need to use artificial intelligence. It may simply be a small program that performs a specific operation reliably.

Examples of possible roles include:

- collecting information from APIs;
- retrieving system information;
- collecting hardware or resource data;
- performing calculations;
- transforming data into a structured format;
- filtering information;
- interacting with databases.

The purpose is to reduce the amount of mechanical work that Viernes has to perform itself.

This allows a relatively small language model to operate as the reasoning and coordination layer without requiring it to become responsible for every specialized operation.

---

Database

The database provides persistent storage for the system.

It is intended to retain information such as:

- tasks;
- task states;
- results;
- verification information;
- errors;
- historical records;
- information collected by bots.

Persistence is important because Viernes should not lose the state of its work simply because the model or computer process has to restart.

The database also provides a historical record that can later be used to analyze system behavior and model errors.

---

Watchdog

The Watchdog is an external process-health component.

Its purpose is not to reason about tasks or evaluate the quality of answers.

It monitors the Viernes process for situations such as:

- unexpected termination;
- excessive generation;
- context-limit failures;
- lack of generation progress;
- other conditions indicating that the process is no longer operating normally.

When a genuine process failure is detected, the Watchdog can restart Viernes.

This separation is intentional:

WATCHDOG  →  Is the process healthy?

CONTROLLER →  Is the task progressing correctly?

REVIEWER   →  Is the result acceptable?

VIERNES    →  Can the problem be reasoned about?

The Watchdog was developed before comparing Viernes with other local AI architectures. Its design came from practical experience with long-running processes and from the limitations observed while running a relatively small local language model.

More information about its origin and evolution is documented separately in "The origin of the watchdog" (watchdog.md).

---

Separation of responsibilities

One of the main architectural principles of Viernes is to avoid giving unrelated responsibilities to the same component.

Component      Main responsibility

Viernes        Reasoning and interaction
Controller     Task lifecycle and coordination
Reviewer       Verification and classification
Bots           Specialized operations
Database       Persistent information
Watchdog       Process health and recovery

This separation is intended to make the system easier to test, modify and understand.

For example, improving the Watchdog should not require changing how task verification works. Similarly, changing an information bot should not require changing the language model itself.

---

Design philosophy

Viernes is being developed around a simple principle:

«Don't build a bigger brain to do everything. Build a better system around the brain you already have.»

A larger language model can provide more capabilities, but increasing model size is not the only way to improve a system.

Another approach is to reduce the amount of work the model needs to perform directly.

Instead of asking Viernes to:

collect information
calculate
store data
monitor processes
verify everything
manage recovery
reason
and interact with the user

the architecture attempts to distribute these responsibilities:

                 ┌──────────────┐
                 │    VIERNES   │
                 │   Reasoning  │
                 └──────┬───────┘
                        │
       ┌────────────────┼────────────────┐
       ▼                ▼                ▼
     BOTS          CONTROLLER         REVIEWER
       │                │                │
       └────────────────┼────────────────┘
                        ▼
                     DATABASE

                     WATCHDOG
                        │
                        ▼
                 Process recovery

This approach is particularly useful when running local AI on modest hardware.

---

Architecture in development

This architecture is not considered finished.

Viernes is being developed experimentally, and components are introduced when a concrete problem justifies them.

The project therefore prioritizes:

1. solving real problems;
2. keeping responsibilities separated;
3. testing components independently;
4. preserving working versions;
5. observing failures;
6. improving the architecture gradually.

The goal is not to reproduce an existing agent framework exactly.

The architecture has emerged through experimentation, practical constraints, comparison with other projects, and the attempt to understand which responsibilities should belong to the model and which should belong to the surrounding system.