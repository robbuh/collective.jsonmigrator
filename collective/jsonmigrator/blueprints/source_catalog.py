# -*- coding: utf-8 -*-
from collective.jsonmigrator import logger
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.interfaces import ISectionBlueprint
from zope.interface import classProvides, implements

import base64
import threading
import time
import urllib
import urllib2
import ast


try:
    import json
except ImportError:
    import simplejson as json

from plone import api


class CatalogSourceSection(object):

    """A source section which creates items from a remote Plone site by
       querying it's catalog.
    """
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.options = options
        self.context = transmogrifier.context

        self.remote_url = self.get_option('remote_url', 'http://localhost:8080')
        self.remote_username = self.get_option('remote_username', 'admin')
        self.remote_password = self.get_option('remote_password', 'admin')

        catalog_path = self.get_option('catalog_path', '/Plone/portal_catalog')
        self.site_path_length = len('/'.join(catalog_path.split('/')[:-1]))

        catalog_query = self.get_option('catalog_query', None)
        catalog_query = ' '.join(catalog_query.split())
        catalog_query = base64.b64encode(catalog_query)

        self.remote_skip_paths = self.get_option('remote_skip_paths','').split()
        self.queue_length = int(self.get_option('queue_size', '10'))

        # Install a basic auth handler
        auth_handler = urllib2.HTTPBasicAuthHandler()
        auth_handler.add_password(realm='Zope',
                                  uri=self.remote_url,
                                  user=self.remote_username,
                                  passwd=self.remote_password)
        opener = urllib2.build_opener(auth_handler)
        urllib2.install_opener(opener)

        req = urllib2.Request(
            '%s%s/get_catalog_results' %
            (self.remote_url, catalog_path), urllib.urlencode(
                {
                    'catalog_query': catalog_query}))

        try:
            f = urllib2.urlopen(req)
            resp = f.read()
        except urllib2.URLError:
            logger.error("Please check if collective.jsonify, collective.jsonmigrator are installed in the remote server and if 'get_item', 'get_children', 'get_catalog_results' external methods are created in remote Plone web site")
            raise

        # Transform resp in list
        resp = ast.literal_eval(resp)

        # Normalize local and remote objects path to check already existing objects
        # Get existing objects in site
        portal_catalog = api.portal.get_tool('portal_catalog')
        results = portal_catalog.searchResults()
        local_path = api.portal.get().absolute_url_path()

        existing_path = [x.getPath() for x in results if local_path in x.getPath()]

        local_path = local_path.split('/')
        remote_path = catalog_path.split('/')

        # if root folder is different from remote root folder (/foder/Plone != /Plone) delete first folder in local existing_path.
        # (probably local Plone site is inside a ZODB Mount Point)
        if resp and local_path[1] != remote_path[1]:
            # Delete first path folder if Plone LOCAL web site is inside a folder or ZODB Mount Point and REMOTE web site is not
            if len(local_path) > 2:
                # Delete first folder and add / at the beggining of the path
                existing_path = ["/"+"/".join(x.strip("/").split('/')[1:]) for x in existing_path]

        # Just in case remote website ID is different from website ID
        site_id_position = len(local_path)-1
        local_id = existing_path[0].split('/')[site_id_position]
        remote_id = resp[0].split('/')[site_id_position]

        if local_id != remote_id:
            existing_path = [x.split('/') for x in existing_path]

            # Replace local_id with remote_id
            for x in existing_path:
                x[site_id_position] = remote_id

            existing_path = ['/'.join(x) for x in existing_path]

        # Avoid already existing objects creation
        resp = [x for x in resp if x not in existing_path]

        # Rebuild folder and subfolder tree hierarchy sorting by folders path length
        resp = sorted(resp, key=lambda x:x.count('/'))

        if not resp:
            logger.warning("*** Nothing to do. All objects are already migrated! ***")

        resp = json.dumps(resp)

        # Stop alphabetical oder
        #self.item_paths = sorted(json.loads(resp))
        self.item_paths = json.loads(resp)


    def get_option(self, name, default):
        """Get an option from the request if available and fallback to the
        transmogrifier config.
        """
        request = getattr(self.context, 'REQUEST', None)
        if request is not None:
            value = request.form.get('form.widgets.' + name.replace('-', '_'),
                                     self.options.get(name, default))
        else:
            value = self.options.get(name, default)
        if isinstance(value, unicode):
            value = value.encode('utf8')
        return value

    def __iter__(self):
        for item in self.previous:
            yield item

        queue = QueuedItemLoader(self.remote_url, self.remote_username, self.remote_password, self.item_paths,
                                 self.remote_skip_paths, self.queue_length)
        queue.start()

        for item in queue:
            if not item:
                continue

            item['_path'] = item['_path'][self.site_path_length:]
            yield item


class QueuedItemLoader(threading.Thread):

    def __init__(self, remote_url, remote_username, remote_password, paths, remote_skip_paths, queue_length):
        super(QueuedItemLoader, self).__init__()

        self.remote_url = remote_url
        self.remote_username = remote_username
        self.remote_password = remote_password
        self.paths = list(paths)
        self.remote_skip_paths = remote_skip_paths
        self.queue_length = queue_length

        self.queue = []
        self.finished = len(paths) == 0

    def __iter__(self):
        while not self.finished or len(self.queue) > 0:
            while len(self.queue) == 0:
                time.sleep(0.0001)

            yield self.queue.pop(0)

    def run(self):
        while not self.finished:
            while len(self.queue) >= self.queue_length:
                time.sleep(0.0001)

            path = self.paths.pop(0)
            if not self._skip_path(path):
                item = self._load_path(path)
                self.queue.append(item)

            if len(self.paths) == 0:
                self.finished = True

    def _skip_path(self, path):
        for skip_path in self.remote_skip_paths:
            if path.startswith(skip_path):
                return True
        return False

    def _load_path(self, path):
        # login via URL to get all object's attributes in get_item method (e.g. "_history")
        item_url = '%s%s/get_item?__ac_name=%s&__ac_password=%s' % (self.remote_url, urllib.quote(path), self.remote_username, self.remote_password)
        try:
            f = urllib2.urlopen(item_url)
            item_json = f.read()
        except urllib2.URLError as e:
            logger.error(
                "Failed reading item from %s. %s" %
                (item_url, str(e)))
            return None
        try:
            item = json.loads(item_json)
        except Exception as e:
            logger.error("-------> Could not decode item from %s." % item_url)
            logger.error(e)
            return None
        return item