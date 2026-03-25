# communicators
History:
I am building a system with many servers and an even greater number of websocket connections.
Faced with this unsustainable complexity of testing and maintaining dozens of websocket connections
I built this communicators library so make connecting any two custom python servers via websockets,
be as easy as specifying the host and port of the current server and the server it needs to initiate 
a connection to.

Version 1:
Intended scale:1-20 users (demo)
Description: A single connection from the customer to the provider servers. This will fail if 
internetcuts out briefly. This is the protoype to pass tests and demo scale demand before 
upgrading to version 2.

Version 2:
Intended scale: up to 20 million users (regional)
Description: Ping system ensures connection reliability, even on spotty customer internet. 
Negative fan out supported. Buffer count and server instance spawning to support high demand.
The only limitations it this required only one public facing IP provider-side and thus does 
not scale to geo-distributed servers.

Version 3:
Intended scale: up to Billions / unlimited users.
Description: Supports Geo-location based routing. Supports distributing load accross a IP pool.

Version 1 is not intended for external use. However I will iterate in public and you are free 
to try it at your own risk. Version 2 will be started as soon as version 1 works, even unreliably.
Version 2 will be intended for general use and should work fine as long as you are not a fortune 
500 company. Version 3 in lowqer priority and may be delayed for several months+ even after version 
2 is complete and tested. I warn you that I am an optumist on timelines, but I hope to complete 
Version 3 some time over this summer 2026.

Why There are soo Few LOC?
IMAO the closer code it to abstract algorithm, the better. longer code is much harder for both 
humans and AI to understand and maintain. So I aim to have no more than 2000 LOC in any 
program and build more libraries or other imports as neccessary to keep and program small. 
I spend a lot of time judiciously assessing whether or not to add code and as a result 
I find way to make a few lines of code get a lot done via abstraction.

What to do if You Want to Contribute?
If you want to contribute, you are welcome to try but I have to warn you. I am very strict with 
how I code. If I do accept yout suggestion, it is more likely that I will take your code as a 
suggestion and build my own equivalent in accordance with my principles. Therefore to increase 
your odds of my taking you seriously, I recomment being very clear on what problem your PR 
fixes, abstractly what algorithm you think is appropriate to fix it and how the algorithm 
is in python. I am bad at spelling, so if your PR is just a spelling fix I may be happy to
fix that.

Should you Trust me?
No, read the code yourself if you have doubts. Never blindly copy and paste. I don't even blindly 
copy and paste my own code. when it comes to versions, by default they should not be considered 
stable. Once a version is stable I will lable it stable for example version 2.3 (stable). Stable 
versions have probably been used at Analysis Labs for 1 month + and have been finally deemed bug 
free as far as I know. At Analysis Labs, policy for open-sourse projects, to iterate in public and
only label a version stable once it has survived use in production for a sufficient length of 
time to rule out common bugs.

Purpose of Communicators
In principle, a server has a few jobs: recieve requests, possible do some work on the incoming 
data, and forward that to the appropriate destination. IT either works or it doesn't It is 
super comlicated under the hood, but there is a pretty simple objective function. Since no 
current library I am aware offers to make servers easy and capable, while making such a 
server is possible in principle, I decided to build the communicators library. It manages 
both persistently terning a normal class into a server and reducign the minimal complexity 
down to merely specifying positive and negative hosts and ports and using predefined input 
and output functions to manage I/O/
