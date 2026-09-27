Why keep the watchdog?

The watchdog is one of the more unusual parts of Viernes, and it deserves some context.

The goal was not to build a sophisticated AI supervisor. The goal was much simpler: keep a small local model usable without having to compensate for its limitations by continuously increasing hardware resources, context size, or system complexity.

A small language model can sometimes spend too much time generating, reach its context limitations, or stop making useful progress while the underlying process is still running.

Instead of trying to solve every one of these situations inside the model itself, Viernes uses an external watchdog to monitor the process.

When a genuine failure condition is detected, the watchdog can intervene and restart the model.

This has an important side effect: the system does not need to keep a large amount of additional control logic inside the model's context.

In other words:

«The watchdog is not there to make the model smarter. It is there so that the model does not need to be smarter just to remain usable.»

This is particularly relevant because Viernes is designed to run on relatively modest local hardware.

Rather than continuously increasing model size, context, or resource consumption to handle every edge case, part of the problem is moved outside the language model and handled by a lightweight system component.

The watchdog is therefore a pragmatic compromise between model limitations, system reliability, and resource efficiency.

It may not be the most elegant solution for every environment, and it may evolve as I learn more about software architecture. But it has been useful for the specific constraints under which Viernes is being developed.