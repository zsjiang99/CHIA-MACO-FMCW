# MACO agent provenance

The four original MACO Python agent modules are not redistributed in this
release candidate. Obtain them from `https://github.com/coredac/MACO`, commit
`31c02ce013838d89ef2a6d211acfdf639ecb178d`, and set `MACO_AGENT_DIR` to
the checkout's `agent/` directory.

`chia_maco.agent_search` injects the local-model transport and the bounded FMCW
validator at runtime. Original agent prompts/classes are retained; the final
evaluator contract narrows their design schema. The original driver, external
synthesis service and shared result files are not used. Each run records SHA-256
hashes of these four modules and the integration adapter.

No root LICENSE was found in the supplied MACO checkout. These upstream files
are not automatically covered by this repository's BSD license.
