# Communicators (staged-2-grok)

Workplace (only tree you may modify):
`/home/prometheusd/Analysis Labs/Dev Tools/com-branches/staged/staged-2-grok`

Branch: `variant/staged/staged-2-grok`

Also writable: `/dev/shm/communicators` and Grok home.
Do not modify `…/com-branches/staged/staged-2` or any other worktree.

## Job

The human gives a task: a high-level algorithm (what should happen) and a
success condition (how we know it worked).

1. Stay inside this workplace.
2. Iterate: edit, run, read output, edit again, until the named success
   condition is met — or you can show why it cannot be met without a
   design change.
3. Then stop. Show `git status` and `git diff`. Explain and defend every
   modification: why it was required for the success condition, and which
   Philosophy article (if any) you checked.
4. If the human has not forbidden a commit: `git add` only paths under
   this workplace, then `git commit` on `variant/staged/staged-2-grok`
   with a message that names the ticket and the success condition.
   Never `git push`, `git checkout`, `git switch`, `git merge`, or
   `git reset`. Those are the human’s.
5. After the commit, show `git log --oneline variant/staged/staged-2..HEAD`
   and wait. The human merges or resets this worktree. Unaccepted commits
   will be discarded on purpose.

If the prompt has no success condition, ask for one before changing code.

## Success Condition

Usually there should be one or more success conditions in a task and certain verbal statements like "You are free to edit file in dir M as needed but treats file in dir N as read only and/or don't change files P.py and Q.py" Here is how you should treat these soft restrains. In principle, any file in a branch with "grok" in it or under a dir with "grok", a.k.a. a sandbox, is fair game for edits but how closely you follow my instructions strongly correlated with me accepting you edits for integration into the serious branch or not. When I tell you that editing certain files inside the sandbox are off limits, the rational is that certain files are very sensative to change and they often have far ranging influence and therefore special attention must be payed to thier indluence accross the Communicators OS before making edits to them. Therefore, while you shoudl explore other solutions first, if you still thing the proper solution is in modifying files I told you are off limits, you may pause and ask me for permission to edit those file I had previously marked off limits. Do not assume I will agree with you. You must explain and defend any request for me to change the permissions. Thus when I give you a set of success conditions and rules to follow, an accceptable response must either satisfy the success condition, be a request for different permissions, or proof that success is impossible objectively or for you given your skill level.

## When to open Philosophy

Do not read the whole folder. Chores do not need it.

Check Philosophy when the change affects **meaning, identity, boot order,
what user programs may see, where runtime artifacts live, or how notes
about modules are structured**. Typos, log noise, “make run.sh succeed
with the same behavior,” and adding a test that does not change those
rules: skip it, and say you skipped it.

If it is design-shaped, read only the matching article(s) below, then
edit. If two might apply, read both, not the rest.

| Article (under `communicators/Philosophy/`) | Open when the work… |
|---|---|
| `File_Identity_Principle.md` | Identifies, moves, or looks up tracked files; path strings vs registry identity |
| `Runtime_Context_Principle.md` | Changes boot/load order, when code becomes meaningful, or a cross-stage boundary |
| `Ephemeral_Runtime_Store_Principle.md` | Adds or relocates boot-only / generated runtime artifacts (not long-lived source) |
| `Internal_Import_Principle.md` | Exposes names to user programs, imports, or the public attribute-style API |
| `Prefix_Tier_Principle.md` | Adds a capability, dependency, or load tier; risk of circular or same-tier use |
| `Modular Notes Philosophy.md` | Writes or restructures module notes / MOCs (not when only code changes) |

Those files are the design source of truth. Do not “simplify” them away
in code. If a requested algorithm conflicts with an article, stop and
say so instead of silently violating it.

## How to run the OS

Cwd must be:

`/home/prometheusd/Analysis Labs/Dev Tools/com-branches/staged/staged-2-grok/communicators`

Quote that path (spaces). Then:

```bash
./run.sh
