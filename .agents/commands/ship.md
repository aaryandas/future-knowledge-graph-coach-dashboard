Run the full check suite for this repo (typecheck, lint, tests — whatever the
package scripts define). If everything is green, commit all staged and
unstaged work with a conventional-commit message, push the branch, and open a
PR against main with a short summary of the diff.

If any check fails, stop and report the failure with its output — do not
commit or push.
