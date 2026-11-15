# What "stateless" means here, and how it was checked

| Claim | How it was checked | Where |
|---|---|---|
| A full run writes no files | File-open and os.open are patched to raise on any write mode (bytecode caches excepted), and the project tree is snapshotted before and after. Runs all 25 gold cases through load, draft, payload preview and a cloud run against a fake model. | tests/test_stateless.py |
| The pipeline opens no network connections | Socket connect is patched to raise and record any attempt. Cloud mode is tested against a fake client, so only the real client could connect. | tests/test_stateless.py, tests/test_app.py |
| Logs and console output contain no document content | Logging is captured at DEBUG, plus stdout and stderr, across all gold cases; the output is searched for planted provider names, every identifier from the source documents, claim numbers and the typed member name and ID. | tests/test_stateless.py |
| The app keeps parsed data only | The set of fields a loaded claim may hold is pinned by a test; the raw file is never kept by our code. | tests/test_app_logic.py |
| "Clear everything" erases the session | The headless app test loads a claim, presses the button, and checks the state is gone. | tests/test_app.py |
| You approve exactly what is sent | The send path compares the payload built at send time with the one shown; any difference cancels before a request. The approval box is a fresh one after every send. | tests/test_app_logic.py, tests/test_app.py |
| The real server wrote nothing | Manual: a marker file is created, the app is used, and `find -newer` lists files modified since. | docs/stateless.md (this section) |

## Known limits (stated honestly)

- Streamlit holds an uploaded file in the server process's memory until it is replaced, cleared, or the tab is closed
  (per Streamlit's own description). Our code does not keep the raw file, but this tool cannot control Streamlit's memory.
- The operating system may swap memory to disk. That cannot be controlled or checked from this project.
- The checks cover this project's code and its libraries during tests. Streamlit's usage statistics are switched off in
  `.streamlit/config.toml`, but I have not audited Streamlit's own network behavior beyond that.
- Streamlit may record a first-run choice in `~/.streamlit/credentials.toml`, outside the project. That is not claim data.
- Cloud mode sends the shown payload to Anthropic. See docs/privacy.md for what that payload contains and how the provider handles it.
