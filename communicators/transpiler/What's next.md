
Synheuresis  
I know what, but not how.  
What I know:

- I already have high level transcription
- I have load and build defined.
- I need to automatically build out the runtime.
- This may require tweaks to the md.
- this may require more advanced _to_ handling.
- This will require processing rather than ignoring line numbers.
- May require AST for combining python blocks/functions.
- This will require more systematic error handling and explaining.  
    Is this enough? Actually this is enough to

Synthesis:  
How next:

- If _to_ is not unique then: ✓
- Convert md lines to python blocks
- Order those blocks by line numbers.
- Possibly via AST.
- Proper indentation required.
- Save to disk or namespace in RAM.