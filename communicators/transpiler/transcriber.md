Mission accomplished we have the high level script now and are moving on to defining load, build, etc.

## Load 

 moves contents of file, namespace or variable to a new variable or namespace or file.
 - This will take a function tree since it must generalize to json, md, txt, etc.
 - 

## Build

uses the with file to extrapolate the object file into destination.
- But in reality build itself remains light weight since it rely on some add hoc program to do the muscle work. 
- thus build transforms into with(object, destination: Path)

# Next

work on on live code running and compilation into runtime code.