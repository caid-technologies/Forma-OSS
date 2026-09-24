# Versioned project links

Set `FORMA_PROJECT_SHARE_SECRET` on the API to a stable random secret of at least
32 bytes (`openssl rand -hex 32`). Use the same value on every API replica. Never
expose it through frontend environment variables. No database migration is needed.
Rotating the key invalidates all links; individual-link revocation is not provided.
Deleting a project also makes its links unavailable.

Owners can share a saved revision from the chat's project surface or project page.
The link uses `/project/<id>/shared?revision=<revision UUID>#share=<capability>`.
The fragment avoids including the capability in HTTP access logs and referrers.
The recipient page reads it and sends `X-Project-Share` to the API. Reverse proxies
must forward this header; API CORS permits it.

Anyone with the complete link can view that design version and its saved CAD,
without signing in. Sharing does not change project visibility, publish chat,
permit editing, list history, or authorize other versions. The viewer omits
private generation metadata, uploaded chat reference imagery, and revision
instructions. Later edits do not change the shared snapshot. A missing or invalid
version fails explicitly instead of loading the latest design. Legacy projects
without immutable revisions must save a version before sharing.
