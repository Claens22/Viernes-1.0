The origin of the watchdog

The watchdog was designed early in the development of Viernes, before I started comparing the project with other local AI and agent architectures.

Its origin was not a specific architecture pattern I had found elsewhere. It came from a practical problem.

I already had experience with long-running processes from mining software, where an external monitor can detect when a process stops responding or terminates unexpectedly and restart it. When I began experimenting with a small local language model, I encountered a different version of the same problem: the model could remain running while generating for too long, reaching its context limits, or becoming effectively stuck.

At that point, I did not yet know a more direct or elegant way to control those situations. So I applied a familiar idea from another domain: keep a lightweight external process watching Viernes and intervene when the process appears unhealthy.

The watchdog therefore became an external component responsible for process health rather than task reasoning.

Only later, when I began comparing Viernes with other local AI and agent projects, I noticed that this particular approach was not a common pattern in the architectures I was looking at. That comparison was useful because it showed me that the watchdog was an unusual architectural decision, but also helped me understand why it had appeared naturally in my project: it solved a very specific problem created by running a relatively small model on limited hardware.

The watchdog has evolved through several versions since then. It also helped lead to a clearer separation of responsibilities:

- Watchdog: process health and recovery.
- Controller: task lifecycle and persistence.
- Reviewer: result verification and classification.
- Viernes: reasoning and interaction.
- Database: persistent information and history.

The important part of this history is that the architecture was not designed from a finished blueprint. It evolved from practical problems, experiments, failures, and later comparison with existing projects.