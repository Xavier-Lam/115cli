# Contributing

## Code Style

- In the long run, the project will get rid of the p115client module. All new code should use `client` to make API calls.
- Code including tests should be maintainable and consistent. Read existing code carefully before making changes and follow the existing style and structure.
- Docstring for private methods or functions is not needed unless the logic is complex.
- Log messages, exception messages should *NOT* be capitalized and *NOT* end with a period, except for a long message with multiple sentences.

### Command Implementation
- Don't catch unexpected exceptions in commands, users should be able to see the full traceback when something unexpected happens.

### Test Implementation
- Do not add docstrings to tests. Comments are permitted when necessary.
- Tests should be grouped in classes.
- Command line tool unit tests should mock API calls. Tests should be simple — verify the command can be executed successfully with expected inputs and outputs. 
- Don't write tests relating to `formatter` for commands, it is `formatter` tests' scope. All commands use formatters should use json formatter to validate the output.

## Testing

- There is an unknown rate limit on API calls. Avoid running API integration tests too frequently. Only run them when your changes directly affect API behaviour. Make requests sent to the API as few as possible.
