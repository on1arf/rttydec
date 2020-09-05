import sys

# python version check
if sys.version_info.major < 3:
	raise RuntimeError("Python3 or newer required")
#end if


"""
rtty decoder
version 0.5.0: 09/aug/2020
(c) Kristoff Bonne (ON1ARF)

This software is open-source licensed under the GPL3.0-or-later license:
https://www.gnu.org/licenses/gpl-3.0-standalone.html


This application is part of a GNU Radio flowgraph to decode RTTY transmissions of
the Deutsche Wetter Service on 147.3 KHz and other frequencies.

As the DWD transmissions contain 1 startbit ('1') and 1.5 stopbits ('0'), the
RTTY signal is demodulated at 100 baud (i.e. twice the 50 baud RTTY speed)

For every 1 'baudot' bit, 2 bits are received from the GNU Radio flowgraph.

Communication from the GNU Radio flowgraph to baudotdec_mc is done via
UDP packets containing 1 bit, as decoded by the flowgraphm, per UDP packet.
the UDP packets are sent towards an ipv4 multicast address.

The default values are:
ip-address: 225.0.0.1
port: 10000


The "rttydec_mc" function can also be used as a standalone function that
can be included as such:
from rttydec_mc import rttdec_mc

Parameters are:
lip, lport: ip-address and UDP port for the ip multicast stream

tcpconnection (optional): TCP-socket connection

flushall (optional): flush output after every character
flushnl (optional): flush output after a cr/lf


"""

import socket
import struct



def __matchbaudot2start3stop(x):
	#match 1 start bit ('1') + 1.5 stop bits ('0')
	#note1: 5 databits
	#note2: all bits are counted double
	return (3+x[0]+x[1]-x[12]-x[13]-x[14])*2+sum([1 if x[p] == x[p+1] else 0 for p in range(2,12,2)])
#end match baud pattern, 2 start, 3 stop



def __findmax(l):
	pos=-1
	maxv=-1
	cnt=-1
	
	for c in range(len(l)):
		val=l[c]
		if val == maxv:
			cnt+=1
		elif val > maxv:
			maxv=val
			pos=c
			cnt=1
		#emd elsid - if
	#end for
	return(maxv,pos,cnt)
#end "find maximum"





class baudotdecoder():
	# International Telex Alphabet 2
	ITA2 = [
		# 'letters table'
		['\x00', 'E', '\n', 'A', ' ', 'S', 'I', 'U',
			'\r', 'D', 'R', 'J', 'N', 'F', 'C', 'K',
			'T', 'Z', 'L', 'W', 'H', 'Y', 'P', 'Q',
			'O', 'B', 'G', None, 'M', 'X', 'V', None],
		#  'numbers table'
		['\x00', '3', '\n', '-', ' ', "'", '8', '7',
			'\r', '\x05', '4', '\x07', ',', '!', ':', '(',
			'5', '+', ')', '2', '£', '6', '0', '1',
			'9', '?', '&', None, '.', '/', '=', None]
		]

	def __init__(self):
		self.state_shift=0
	#end if
	
	def decode(self,vin):
		v=31-(vin[1]+vin[3]*2+vin[5]*4+vin[7]*8+vin[9]*16)


		if v == 27:
			self.state_shift=1
			return None
		elif v == 31:
			self.state_shift=0
			return None
		else:
			return self.ITA2[self.state_shift][v]
		#end else - elif - if
	#end def
#end class baudotdecode



def __bytes_to_intlist(b):
	# convert bytearray (containing list of either 0x00 or 0x01 to list of 0 or 1)
	tmp=struct.unpack('b'*(len(b)),b) # strip the '0x' from the start, convert to (48,48) for '00' or (48,49)' for '01'
	return [x-48 for x in tmp[1::2]]
#end def __bytes_to_int


def rttydec_mc(lip,lport,tcpconnection=None, flushall=True, flushnl=True):

	# if "flushall", also flush cr/lf
	if flushall: flushnl=True

	# receiving multicast in python, shameless stolen from
	# https://stackoverflow.com/questions/603852/how-do-you-udp-multicast-in-python

	# assert bind_group in groups + [None], \
	#     'bind group not in groups to join'
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

	# allow reuse of socket (to allow another instance of python to run this
	# script binding to the same ip/port)
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

	sock.bind(('',lport)) # bind to any ip-address


	#igmp join
	mreq=struct.pack('4sl',socket.inet_aton(lip),socket.INADDR_ANY)
	sock.setsockopt(socket.IPPROTO_IP,socket.IP_ADD_MEMBERSHIP,mreq)


	# here starts the actual baudot decoder

	buf=[bytes(0) for x in range(31)] # create buffer
	
	nbytes=31
	startpos=0
	restdata=[]

	mybaudot=baudotdecoder()
	
	buf=[]
	while True:
		#receive data
		newbytes = sock.recv(10240)

		for inbyte in struct.unpack('B'*len(newbytes),newbytes):

			buf.append(inbyte)
		
			if len(buf) < 29: continue # read up to 29 bytes

			v=[__matchbaudot2start3stop(buf[p:p+15]) for p in range(0,14)]
			(maxv,pos,cnt)=__findmax(v)

			b=mybaudot.decode(buf[pos+2:pos+12]) # skip 2 start bits
			if b:
				if b == '\n':
					if tcpconnection:
						try:
							tcpconnection.sendall('\n'.encode('utf-8'))
						except BrokenPipeError:
							tcpconnection.close()
							exit
						except OSError:
							tcpconnection.close()
							exit
						#end try
					else:
						# no tcp connection -> just print it
						print('',flush=flushnl)
					#end if
				elif b == '\r':
					pass
				else:
					if tcpconnection:
						try:
							tcpconnection.sendall(b.encode('utf-8'))
						except BrokenPipeError:
							tcpconnection.close()
							exit
						except OSError:
							tcpconnection.close()
							exit
						#end try
					else:
						# not via tcp connection, just print it
						print(b,end='',flush=flushall)
					#end if
				#end if - elif - else
			#end if

			buf=buf[pos+15:]

		# end for

	#end while		

#end def "main"

def Main():
	ipaddr="225.0.0.1"
	port=10000
	rttydec_mc(lip=ipaddr,lport=port)
#end main

if __name__ == "__main__": Main()

