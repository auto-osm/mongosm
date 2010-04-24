import sys
import os
import shelve
import time
import pymongo
from datetime import datetime
from xml.sax import make_parser
from xml.sax.handler import ContentHandler
from pymongo import Connection

class OsmHandler(ContentHandler):
    def __init__(self, client, shelf):
        self.record = {}
        self.client = client
        self.client.osm.nodes.ensure_index([('loc', pymongo.GEO2D), ('id', pymongo.ASCENDING)])
        self.client.osm.nodes.ensure_index([('id', pymongo.ASCENDING), ('version', pymongo.ASCENDING)])
        self.client.osm.ways.ensure_index([('id', pymongo.ASCENDING), ('version', pymongo.ASCENDING)])
        self.client.osm.relations.ensure_index([('id', pymongo.ASCENDING), ('version', pymongo.ASCENDING)])
        self.shelf = shelf

    def fillDefault(self, attrs):
        self.record['id'] = long(attrs['id'])
        self.record['timestamp'] = self.isoToTimestamp(attrs['timestamp'])
        self.record['tags'] = {}
        if attrs.has_key('user'):
            self.record['user'] = attrs['user']
        if attrs.has_key('uid'):
            self.record['uid'] = long(attrs['uid'])
        if attrs.has_key('version'):
            self.record['version'] = int(attrs['version'])
        if attrs.has_key('changeset'):
            self.record['changeset'] = long(attrs['changeset'])

    def isoToTimestamp(self, isotime):
        t = datetime.strptime(isotime, "%Y-%m-%dT%H:%M:%SZ")
        return time.mktime(t.timetuple())

    def startElement(self, name, attrs):
        if name == 'node':
            self.fillDefault(attrs)

            self.record['loc'] = {'lat': float(attrs['lat']), 'lon': float(attrs['lon'])}
        elif name == 'changeset':
            self.fillDefault(attrs)
        elif name == 'tag':
            # MongoDB doesn't let us have dots in the key names.
            k = attrs['k']
            k = k.replace('.', ',,')
            self.record['tags'][k] = attrs['v']
        elif name == 'way':
            self.fillDefault(attrs)
            self.record['nodes'] = []
        elif name == 'relation':
            self.fillDefault(attrs)
            self.record['members'] = []
        elif name == 'nd':
            ref = long(attrs['ref'])
            self.record['nodes'].append(ref)

            nodes2ways = self.client.osm.nodes.find_one({ 'id' : ref })
            if nodes2ways:
                if 'ways' not in nodes2ways:
                    nodes2ways['ways'] = []
                nodes2ways['ways'].append(self.record['id'])
                self.client.osm.nodes.save(nodes2ways)
            else:
                print "Node %d ref'd by way %d not in file." % (ref, self.record['id'])
        elif name == 'member':
            ref = long(attrs['ref'])
            member = {'type': attrs['type'],
                      'ref':  ref,
                      'role': attrs['role']}
            self.record['members'].append(member)
            
            if attrs['type'] == 'way':
                ways2relations = self.client.osm.ways.find_one({ 'id' : ref})
                if ways2relations:
                    if 'relations' not in ways2relations:
                        ways2relations['relations'] = []
                    ways2relations['relations'].append(self.record['id'])
                    self.client.osm.ways.save(ways2relations)
            elif attrs['type'] == 'node':
                nodes2relations = self.client.osm.nodes.find_one({ 'id' : ref})
                if nodes2relations:
                    if 'relations' not in nodes2relations:
                        nodes2relations['relations'] = []
                    nodes2relations['relations'].append(self.record['id'])
                    self.client.osm.nodes.save(nodes2relations)
        
    def endElement(self, name):
        if name == 'node':
            #if str("node_%s" % (self.record['id'])) in self.shelf:
            #    print "Skipping node %s." % (self.record['id'])
            #else:
            self.client.osm.nodes.save(self.record)
            self.record = {}
                #self.shelf[str("node_%s" % self.record['id'])] = self.record
            #print "Sent node %s." % (self.record)
        elif name == 'way':
            #if str("way_%s" % (self.record['id'])) in self.shelf:
            #    print "Skipping way %s." % (self.record['id'])
            #else:
                self.client.osm.ways.save(self.record)
                self.record = {}
                #self.shelf[str("way_%s" % self.record['id'])] = self.record
                #print "Sent way %s." % (self.record)
        elif name == 'relation':
            self.client.osm.relations.save(self.record)
            self.record = {}

if __name__ == "__main__":

    filename = sys.argv[1]

    if not os.path.exists(filename):
        print "Path %s doesn't exist." % (filename)
        sys.exit(-1)

    #shelf = shelve.open("%s.db" % (filename))
    shelf = ""

    client = Connection()
    parser = make_parser()
    handler = OsmHandler(client, shelf)
    parser.setContentHandler(handler)
    parser.parse(open(filename))
    client.disconnect()
