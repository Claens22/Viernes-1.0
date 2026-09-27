Viernes — Development History

This document records how Viernes evolved during development.

Viernes was not designed from a complete technical specification. Its architecture emerged gradually as practical problems appeared, solutions were tested, and the limitations of those solutions became visible.

The purpose of this document is to preserve that process.

---

1. The beginning — A small local model

Viernes started as an experiment to see how useful a relatively small local language model could become when running on modest hardware.

The goal was not to build the largest possible AI system.

The idea was almost the opposite:

«How much can be achieved by taking a relatively small model and building a useful system around it?»

The initial model used for Viernes was a 4B parameter local model running through "llama.cpp".

This immediately imposed practical limitations.

A small local model has less capacity for complex reasoning and a smaller margin for handling large contexts and difficult tasks than much larger models.

Because the system was intended to run locally and continuously, resource consumption also mattered.

The objective was therefore not simply to make the model answer questions, but to make it operate reliably within relatively restricted computing resources.

---

2. Trying to control hallucinations

One of the first priorities was reliability.

I did not want Viernes to simply produce an answer whenever it could not establish that the information was correct.

The initial system instructions therefore became relatively strict about:

- not inventing information;
- not pretending to know information that was unavailable;
- not claiming that an action had been performed when it had not;
- distinguishing known information from uncertainty;
- avoiding fabricated user or project-specific information.

The intention was straightforward:

«If Viernes does not know something, it should be able to say that it does not know rather than filling the gap with invented information.»

However, testing revealed an important side effect.

A small model can interpret very strict instructions too literally.

Instead of simply becoming more cautious, Viernes could become excessively restrictive and refuse questions that it could actually answer using its general knowledge or reasoning abilities.

This became one of the first lessons of the project:

«Preventing hallucinations is not the same thing as preventing the model from answering.»

The system needed to distinguish between information that should not be invented, information the model could reasonably know, logical deductions, hypotheses and genuinely unknown information.

---

3. The generation problem

Another problem appeared during testing.

When Viernes encountered a difficult task or became caught between its instructions and what it was trying to produce, it could sometimes continue generating for an excessive amount of time.

In the most problematic cases, this behaviour resembled a loop or what I informally began calling "rumination".

This was not just a quality problem.

It was also a resource-management problem.

While the model continued generating, it could consume CPU/GPU resources, occupy the inference process and prevent Viernes from moving on to other work.

This was particularly important because the system was intended to operate continuously on relatively modest hardware.

At that point, I did not have a clean internal mechanism for telling the model:

«"You are no longer making useful progress. Stop and recover."»

A solution was therefore needed outside the model itself.

---

4. The first watchdog

The first solution was an external watchdog.

The idea came partly from previous experience with long-running mining software.

In that environment, an external process can monitor a program and restart it when it stops behaving correctly.

The same basic idea was applied to Viernes.

Instead of asking the language model to recognize and recover from its own problematic generation, a separate lightweight process would monitor it:

VIERNES
   │
   ▼
WATCHDOG
   │
   ├── working normally → continue
   │
   └── abnormal behaviour → intervene/restart

The watchdog was therefore not originally designed as an AI controller, task manager or reviewer.

It was a practical safety mechanism.

Its purpose was to keep Viernes usable and prevent a limited local model from consuming resources indefinitely when it stopped making useful progress.

---

5. Developing the watchdog

The first watchdog was deliberately simple.

However, testing quickly showed that monitoring a language model is more complicated than monitoring a conventional long-running process.

A process can still be alive while Viernes is not actually functioning correctly.

It can be running while:

- generating excessively;
- making no useful progress;
- reaching its context limit;
- repeatedly failing;
- or getting stuck on the same task.

The watchdog therefore evolved through several versions.

Its detection mechanisms became progressively more specific, including generation time, lack of token progress, context-limit errors and repeated failures involving the same task.

The current stable reference is V7.3.

The important point is that V7.3 was not designed as a finished architecture from the beginning.

It grew through testing and through the failure modes discovered during real use.

---

6. The watchdog and the launcher

During the development of the watchdog, another practical problem appeared.

The first versions of the watchdog were started manually in a separate command window from Viernes.

This was useful during development because the watchdog could be observed independently.

However, it meant that two processes had to be started separately:

VIERNES
   │

WATCHDOG
   │

For a system intended to remain available continuously, this was inconvenient.

Both processes needed to operate together.

This led to the creation of the Viernes launcher.

The launcher was not originally designed as part of a large software architecture.

It appeared because the development of the watchdog created a simple operational requirement:

«Viernes and its watchdog needed to start together.»

The structure became:

             LAUNCHER
              /     \
             ▼       ▼
         VIERNES   WATCHDOG

---

7. Running the watchdog in the background

Once the launcher was working, another usability issue became apparent.

There was no reason for the watchdog's command window to remain visible during normal operation.

The watchdog was infrastructure rather than part of the user interface.

The launcher was therefore adapted to start the watchdog in the background.

The result was:

USER
 │
 ▼
VIERNES
 │
 └──────► WATCHDOG
              │
              └── running in background

The watchdog's purpose did not change.

Only the way it was started changed.

---

8. Automatic startup

The next step was making the system persistent.

If Viernes was intended to operate continuously, manually starting everything after every Windows restart was not ideal.

The launcher was therefore connected to Windows startup.

The runtime environment became:

Windows
   │
   ▼
Launcher
   │
   ├──► Viernes
   │
   └──► Watchdog
             │
             └── monitors Viernes

At this point, Viernes was no longer simply a model running from a command line.

It had begun to acquire infrastructure around it.

---

9. Discovering the limits of the watchdog

As development continued, an important distinction became clear.

The watchdog could determine that something was wrong with the Viernes process.

But that did not mean it should understand the task Viernes was performing.

For example, a process failure and a bad answer are fundamentally different problems.

The watchdog should answer:

«"Is the process healthy?"»

It should not become responsible for answering:

«"Was the task completed correctly?"»

Trying to make the watchdog responsible for both would gradually turn it into a second controller.

This led to an important architectural principle:

«Process health and task management should remain separate responsibilities.»

---

10. The need for persistent task state

The next problem appeared when considering what happens after a restart.

Restarting Viernes can solve a process problem.

But it does not automatically solve the question:

«What was Viernes doing before the restart?»

If task information only exists inside the model's current context, a restart can lose the state of the work.

This led to the idea of persistent task states:

INBOX
  │
  ▼
PROCESSING
  │
  ├──────────► VERIFIED
  │
  └──────────► REVIEW

The state of the task therefore needs to exist outside the model.

This was the beginning of the idea of a dedicated Controller and persistent database.

---

11. The Controller

The Controller emerged from the realization that the watchdog should remain focused on process health.

Its responsibility is different.

WATCHDOG
    │
    └── "Is Viernes healthy?"

CONTROLLER
    │
    ├── "What task is being processed?"
    ├── "What state is it in?"
    └── "What should happen next?"

The Controller is intended to manage the lifecycle of tasks, coordinate their processing and preserve their state.

The separation prevents the watchdog from becoming responsible for the entire application.

---

12. The Reviewer

Another problem appeared when considering the long-term database.

If Viernes generates incorrect information and that information is automatically stored as trusted data, the database can become contaminated.

This is particularly important because accumulated errors can later be useful for understanding the model's weaknesses and potentially creating controlled evaluation or future training datasets.

Therefore, model output should not automatically be considered verified simply because Viernes produced it.

This led to the idea of a separate Reviewer:

                 VIERNES
                    │
                  result
                    ▼
                REVIEWER
                 /     \
                ▼       ▼
           VERIFIED    REVIEW

The Reviewer is intended to classify results according to defined verification criteria.

An incorrect result should not necessarily be deleted.

Preserving the original output, together with its classification and available evidence, can provide useful information about model failures.

This also reinforces another principle:

«Unverified does not necessarily mean incorrect.»

If something cannot currently be verified, it may need review rather than automatic rejection.

---

13. Specialized information bots

As the architecture developed, another principle became increasingly clear:

«The language model does not need to perform every operation itself.»

A small specialized program can often collect information, perform a deterministic calculation or transform data more efficiently than asking the language model to do the same work.

This led to the concept of specialized bots.

A bot does not necessarily need to use AI.

It can simply be a lightweight program dedicated to a specific task.

Examples include:

- collecting information from APIs;
- retrieving system and hardware information;
- performing calculations;
- transforming data;
- filtering information;
- interacting with databases.

The objective is to reduce the amount of mechanical work Viernes needs to perform directly.

This allows the language model to concentrate more on reasoning, interpretation and interaction.

---

14. The architecture that emerged

The resulting architecture can be summarized as:

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
                           ▼
                    ┌─────────────┐
                    │   REVIEWER  │
                    └──────┬──────┘
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
              VERIFIED            REVIEW
                  │                 │
                  └────────┬────────┘
                           ▼
                       DATABASE


       SPECIALIZED BOTS
              │
              ▼
           VIERNES


       WATCHDOG
           │
           ▼
    Process health
    and recovery

Each component exists because a specific requirement or problem appeared during development.

The architecture was therefore discovered progressively rather than designed completely in advance.

---

15. Comparing Viernes with other projects

Only after much of this architecture had already developed did I begin comparing Viernes with other local AI and agent projects.

That comparison showed that many individual concepts used by Viernes are established ideas:

- task orchestration;
- persistent memory;
- specialized tools;
- verification;
- human-in-the-loop systems;
- state-based task management.

It also showed that some specific decisions in Viernes are less common among the projects examined, particularly the use of an external watchdog focused on the health of the local LLM process.

This was useful because it provided an external point of comparison for decisions that had originally been made without reference to those projects.

The watchdog, in particular, had been created before that comparison.

It was not added because another agent architecture used it.

It appeared naturally from the practical constraints of Viernes and from the need to keep a small local model operating reliably.

---

16. The current philosophy

The architecture continues to evolve.

One principle has become increasingly important:

«Do not add complexity unless there is a concrete problem that requires it.»

If a responsibility can be handled reliably by a simple component, there is no reason to make the language model responsible for it.

If a component begins to accumulate unrelated responsibilities, that is a signal that the architecture may need to be reconsidered.

Viernes is therefore not intended to be a perfect architecture designed from the beginning.

It is an experimental system whose structure has emerged through:

- practical problems;
- testing;
- failures;
- resource limitations;
- iteration;
- comparison with other projects;
- and gradually improving understanding.

The goal is not to claim that every architectural decision is optimal.

The goal is to document how the system evolved, why decisions were made, and what was learned from them.