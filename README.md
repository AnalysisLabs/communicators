# communicators
History:
I am building a system with many servers and an even greater number of websocket connections. Faced with this unsustainable complexity of testing and maintaining dozens of websocket connections I built this communicators library so make connecting any two custom python servers via websockets, be as easy as specifying the host and port of the current server and the server it needs to initiate a connection to.

What to do if You Want to Contribute?
If you want to contribute, you are welcome to try but I have to warn you. I am very strict with how I code. If I do accept yout suggestion, it is more likely that I will take your code as a 
suggestion and build my own equivalent in accordance with my principles. Therefore to increase  your odds of my taking you seriously, I recomment being very clear on what problem your PR fixes, abstractly what algorithm you think is appropriate to fix it and how the algorithm is in python. I am bad at spelling, so if your PR is just a spelling fix I may be happy to fix that.

Should you Trust me?
No, read the code yourself if you have doubts. Never blindly copy and paste. I don't even blindly copy and paste my own code. when it comes to versions, by default they should not be considered stable. Once a version is stable I will lable it stable for example version 2.3 (stable). Stable versions have probably been used at Analysis Labs for 1 month + and have been finally deemed bug free as far as I know. At Analysis Labs, policy for open-sourse projects, to iterate in public and only label a version stable once it has survived use in production for a sufficient length of time to rule out common bugs.

Purpose of Communicators
In principle, a server has a few jobs: recieve requests, possible do some work on the incoming data, and forward that to the appropriate destination. IT either works or it doesn't It is super comlicated under the hood, but there is a pretty simple objective function. Since no current library I am aware offers to make servers easy and capable, while making such a server is possible in principle, I decided to build the communicators library. It manages both persistently terning a normal class into a server and reducign the minimal complexity down to merely specifying positive and negative hosts and ports and using predefined input and output functions to manage I/O.
