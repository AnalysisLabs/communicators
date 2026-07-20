Ok, so I need unix sockets between the namespace server and the other servers. However there is merit is starting out with http then upgrade to unix-socket once it is working. there is little to lose with this course of action due to how easy to use http is enabling me to develop the transponder without the distraction of connection issues as long as I separate the transponder from the connection method. 

Thus the question becomes, "At what point does it make sense to consider the namespace internals complete and then pivot to making the unix-socket connection working."

In response, i say that that fundamentally that would be when the namespace server has successfully accepted the dumps from the metamorphosis process. At that point it will be important to nail the connections anyway so it will be timely to figure out the unix_socket shit, but also this httpx detour will enable me to offer httpx connections as a supported connection type, whether or not that is advantageous for anyone to use it. 

conclusion: 
- V1
	- http
	- json
- V2
	- unix_socket
	- NumPy