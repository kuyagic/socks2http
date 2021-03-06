#!/usr/bin/env python2
# -*- coding: utf-8 -*-

__version__ = "0.1"

import BaseHTTPServer
import select
import socket
import SocketServer
import urlparse
import socks
import sys
import getopt


class ProxyHandler (BaseHTTPServer.BaseHTTPRequestHandler):

    __base = BaseHTTPServer.BaseHTTPRequestHandler
    __base_handle = __base.handle

    server_version = "socks2http/" + __version__
    rbufsize = 0   # self.rfile Be unbuffered

    def handle(self):
        (client_ip, _port) = self.client_address
        if hasattr(self,
                'allowed_clients') and client_ip not in self.allowed_clients:
            self.raw_requestline = self.rfile.readline()
            if self.parse_request():
                self.send_error(403)
        else:
            self.__base_handle()

    def _connect_to(self, netloc, soc):
        i = netloc.find(':')
        if i >= 0:
            host_port = netloc[:i], int(netloc[i + 1:])
        else:
            host_port = netloc, 80
        print "\tconnect to %s:%d" % host_port
        try:
            soc.connect(host_port)
        except socket.error, arg:
            try:
                msg = arg[1]
            except TypeError:
                msg = arg
            self.send_error(404, msg)
            return 0
        return 1

    def do_CONNECT(self):
        soc = socks.socksocket()
        soc.setproxy(socks.PROXY_TYPE_SOCKS5, self.socks_host,
                port=self.socks_port)
        try:
            if self._connect_to(self.path, soc):
                self.log_request(200)
                self.wfile.write(self.protocol_version +
                                 " 200 Connection established\r\n")
                self.wfile.write("Proxy-agent: %s\r\n" % self.version_string())
                self.wfile.write("\r\n")
                self._read_write(soc, 300)
        finally:
            soc.close()
            self.connection.close()

    def do_GET(self):
        (scm, netloc, path, params, query, fragment) = urlparse.urlparse(
            self.path, 'http')
        if scm != 'http' or fragment or not netloc:
            self.send_error(400, "bad url %s" % self.path)
            return
        soc = socks.socksocket()
        soc.setproxy(socks.PROXY_TYPE_SOCKS5, self.socks_host,
                port=self.socks_port)
        try:
            if self._connect_to(netloc, soc):
                self.log_request()
                soc.send("%s %s %s\r\n" % (
                    self.command,
                    urlparse.urlunparse(('', '', path, params, query, '')),
                    self.request_version))
                self.headers['Connection'] = 'close'
                del self.headers['Proxy-Connection']
                for key_val in self.headers.items():
                    soc.send("%s: %s\r\n" % key_val)
                soc.send("\r\n")
                self._read_write(soc)
        finally:
            soc.close()
            self.connection.close()

    def _read_write(self, soc, max_idling=20):
        iw = [self.connection, soc]
        ow = []
        count = 0
        while 1:
            count += 1
            (ins, _, exs) = select.select(iw, ow, iw, 3)
            if exs:
                break
            if ins:
                for i in ins:
                    if i is soc:
                        out = self.connection
                    else:
                        out = soc
                    data = i.recv(8192)
                    if data:
                        out.send(data)
                        count = 0
            else:
                print "\t" "idle", count
            if count == max_idling:
                break

    do_HEAD = do_GET
    do_POST = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET


class ThreadingHTTPServer (SocketServer.ThreadingMixIn,
                           BaseHTTPServer.HTTPServer):
    pass


def print_usage(code=0):
    print sys.argv[0], "socks_host socks_port \
[port [allowed_client_name ...]]"
    sys.exit(code)

if __name__ == '__main__':
    sys.tracebacklimit = 0
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", ["help"])
    except getopt.GetoptError, err:
        print str(err)
        print_usage(2)

    for o, a in opts:
        if o in ("-h", "--help"):
            print_usage(2)
        else:
            assert False, "unhandled option"

#    if len(args) < 2:
#        print_usage(2)
    ProxyHandler.socks_host = "127.0.0.1"
    if args[0:]:
        ProxyHandler.socks_host = args[0]
    ProxyHandler.socks_port = 9050
    if args[1:]:
        ProxyHandler.socks_port = int(args[1])
    
    port = 8081

    if args[2:]:
        port = int(args[2])
        allowed = []
        for name in args[3:]:
            client = socket.gethostbyname(name)
            allowed.append(client)
            print "Accept: %s (%s)" % (client, name)
        if len(allowed) > 0:
            ProxyHandler.allowed_clients = allowed
        del args[2:]
    else:
        print "[+] Any clients will be served..."

    ProxyHandler.protocol_version = "HTTP/1.0"
    try:
        httpd = ThreadingHTTPServer(('', port), ProxyHandler)
        sa = httpd.socket.getsockname()
        print "[!]", "socks2http", "listening on", sa[0], "port", sa[1], "..."
        print "[!]", "Upstream Socks Server",ProxyHandler.socks_host,"port",ProxyHandler.socks_port
        httpd.serve_forever()
    except Exception as e:
        print e
