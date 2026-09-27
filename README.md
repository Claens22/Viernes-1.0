Viernes

An experimental local AI assistant built around a small language model and a modular architecture.

«Learning by building something real.»

---

About the project

Viernes is a personal experimental project focused on local AI, automation, system monitoring, task management, and modular software architecture.

The project explores an idea:

«Instead of making the AI require more and more resources to do everything itself, make it need to do fewer things directly.»

Viernes is built around a relatively small local language model, supported by specialized software components that handle tasks the model does not need to perform itself.

The project is still under development.

---

Why "Viernes"?

The name comes from Friday, the character from Daniel Defoe's Robinson Crusoe.

The name reflects the original idea behind the project: an assistant that works alongside its user rather than trying to replace them.

The name is not a reference to Marvel's FRIDAY or the MCU.

---

Architecture

The long-term architecture is based on several independent components:

                         USER
                           │
                           ▼
                    ┌─────────────┐
                    │  CONTROLLER │
                    └──────┬──────┘
                           │
                           ▼
                      ┌─────────┐
                      │ VIERNES │
                      │   AI    │
                      └────┬────┘
                           │
                       result
                           ▼
                    ┌─────────────┐
                    │   REVIEWER  │
                    └──────┬──────┘
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
             VERIFIED             REVIEW

Around this core, specialized components can provide information and services:

                    ┌──────────────┐
                    │ Information  │
                    │     Bots     │
                    └──────┬───────┘
                           │
                           ▼
┌──────────┐        ┌─────────────┐        ┌───────────┐
│ Database │◄──────►│ CONTROLLER  │◄──────►│  VIERNES  │
└──────────┘        └──────┬──────┘        └───────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   REVIEWER  │
                    └─────────────┘

                    ┌─────────────┐
                    │  WATCHDOG   │
                    │ system      │
                    │ supervision │
                    └─────────────┘

The architecture is intentionally modular.

A bot can be replaced or improved without requiring the language model itself to be replaced.

---

Core components

🧠 Local AI

Viernes currently runs using a relatively small local language model through "llama.cpp".

The model is intended to provide:

- Natural-language interaction
- Reasoning
- Task interpretation
- Coordination
- Decision support

The model is not expected to perform every specialized operation itself.

---

🤖 Information bots

Specialized bots are intended to collect, transform, calculate, or prepare information before it reaches the model.

Examples could include:

- System information
- CPU/GPU information
- External APIs
- Market or economic data
- Calculations
- Data transformation
- Database operations

The goal is to keep repetitive and mechanical work outside the language model.

---

🎛️ Controller

The controller is responsible for task management, rather than model inference.

The planned task lifecycle is:

INBOX
  │
  ▼
PROCESSING
  │
  ├──────────────► VERIFIED
  │
  └──────────────► REVIEW

The controller is intended to provide persistent task state and recovery after interruptions or restarts.

---

🔎 Reviewer

The reviewer is responsible for evaluating generated results.

A result should not become trusted simply because the model claims that it is correct.

The reviewer is intended to distinguish between:

- Verified information
- Incorrect results
- Uncertain results
- Missing information
- Potential hallucinations
- Results requiring human review

An important goal is to preserve useful error information rather than simply deleting failed outputs.

Errors can become valuable data for future testing and model improvement.

---

🐕 Watchdog

The watchdog has a deliberately narrow responsibility:

«Keep Viernes running.»

It monitors the health of the Viernes process and can restart it when it detects conditions such as:

- Context-size failures
- Generation stalls
- Excessive generation time
- Certain abnormal process states

The watchdog is not intended to understand the meaning of tasks or decide whether an answer is correct.

That responsibility belongs to the controller and reviewer.

---

💾 Database

A persistent database is planned to store information such as:

- Tasks
- Results
- Verification status
- Errors
- Historical information
- System data
- Useful knowledge

The database is intended to become Viernes' persistent memory rather than relying exclusively on the language model's context window.

---

Hardware philosophy

Viernes is being designed around a relatively modest local computer.

The objective is not simply to use a larger model and more powerful hardware to solve every problem.

Instead:

Small model
     +
Specialized tools
     +
Bots
     +
Database
     +
Controller
     +
Reviewer
     =
More capable system

This allows the system to remain relatively lightweight while its capabilities grow through additional components.

---

Development approach

This project is also a way for me to learn programming.

I am not a professional programmer.

I use AI tools as development assistance for:

- Generating code
- Modifying code
- Understanding code
- Debugging
- Exploring possible solutions

However, the development process also involves defining the requirements, designing the architecture, testing the system on real hardware, identifying failures, deciding what should change, and verifying the resulting behavior.

One of my goals is to progressively understand more of the implementation myself and become less dependent on generated code.

---

Current status

🚧 Early development

The project is being developed incrementally.

Current areas of development include:

- [x] Local language model
- [x] Basic launcher
- [x] Process watchdog
- [x] Automatic startup
- [x] Initial system architecture
- [ ] Task controller
- [ ] Reviewer
- [ ] Persistent task database
- [ ] Task recovery
- [ ] Information bots
- [ ] End-to-end integration
- [ ] Deployment/installation system

The checklist will change as the project evolves.

---

Project structure

The planned repository structure is approximately:

Viernes/
│
├── core/
├── bots/
├── controller/
├── reviewer/
├── watchdog/
├── launcher/
├── database/
├── tests/
├── docs/
│
├── README.md
└── LICENSE

The actual structure may change during development.

---

What this project is not

Viernes is currently not:

- A commercial AI product
- A professional enterprise system
- A replacement for cloud AI services
- A fully autonomous artificial general intelligence
- A finished software project

It is an evolving experiment and a practical programming-learning project.

---

Why publish it?

I want GitHub to serve as both a development platform and a record of the learning process.

The repository will document not only successful implementations, but also:

- Problems
- Failed approaches
- Architectural changes
- Experiments
- Tests
- Lessons learned

I believe that showing how a project evolves can be more useful than presenting only the final result.

If you find something that can be improved, simplified, or corrected, constructive feedback is welcome.

---

Philosophy

The central idea behind Viernes can be summarized simply:

«Don't build a bigger brain to do everything. Build a better system around the brain you already have.»

---
## Documentation

- [Architecture](docs/arquitectura.md)
- [Development history](docs/development-history.md)
- [The origin of the watchdog](docs/watchdog.md)

Status: Experimental / In development
Author: Claens