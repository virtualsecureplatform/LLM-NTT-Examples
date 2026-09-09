# Bounded LLM acquisition

The realistic policy study was cancelled at the user's request after 85 completed evaluations. Its results and interrupted active attempt remain in `build/realistic-policy-study-v2`; the study has not been restarted.

The four recorded acquisition failures all contained duplicate legal IDs in otherwise valid JSON rankings. None contained an unknown ID. The old error message combined these two causes. Asking for 35–48 ranked IDs was unnecessary for sequential acquisition, which immediately evaluated only the first choice.

Live policy trials now request exactly one candidate. The call supplies a JSON schema whose allowed values are the current legal IDs and whose array length is exactly one. Other ranking callers retain their requested ranking length. Local validation still rejects unknown IDs, duplicates, wrong lengths, extra properties and truncated responses. Omitted candidates retain their original order after the validated prefix; they are not silently substituted for an invalid LLM choice.

An invalid response gets one corrective retry within the original shared call deadline. Both attempts and validation errors are saved. Repeated invalid output fails explicitly; there is no random or enumeration fallback presented as an LLM selection. HTTP failures remain explicit and do not silently disable schema constraints.

The four previously failed acquisition contexts are exercised against the configured endpoint without launching hardware evaluations. These are API regression checks using saved observations, not fresh architecture-search performance results. The existing study's frozen code and measurements remain unchanged. Timing closure is a separate unresolved generator issue.

Validation: all 160 Python tests pass. All four saved failure contexts returned schema-valid single choices on the first live request; requests, responses and validation records are published in `docs/measured-evidence/llm-single-choice-check`.
