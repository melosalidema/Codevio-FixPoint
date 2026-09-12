"""The untrusted agent side: parser, planner, and run engine.

Everything here may be influenced by attacker-controlled text. It can propose
and rehearse, but it cannot authorize: every mutation goes through
:mod:`app.safety.gateway`.
"""
