# -*- coding: utf-8 -*-
from collective.jsonmigrator import logger
from Acquisition import aq_base
from Products.CMFPlone.utils import safe_unicode
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.utils import defaultKeys
from collective.transmogrifier.utils import Matcher
from collective.transmogrifier.utils import traverse
from ZODB.POSException import ConflictError
from zope.interface import classProvides
from zope.interface import implements
import pytz
import time
from dateutil import parser
from datetime import timedelta
from DateTime import DateTime



class Properties(object):

    """ """

    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.transmogrifier = transmogrifier
        self.name = name
        self.options = options
        self.previous = previous
        self.context = transmogrifier.context

        if 'path-key' in options:
            pathkeys = options['path-key'].splitlines()
        else:
            pathkeys = defaultKeys(options['blueprint'], name, 'path')
        self.pathkey = Matcher(*pathkeys)

        if 'properties-key' in options:
            propertieskeys = options['properties-key'].splitlines()
        else:
            propertieskeys = defaultKeys(
                options['blueprint'], name, 'properties')
        self.propertieskey = Matcher(*propertieskeys)

    def __iter__(self):
        for item in self.previous:
            pathkey = self.pathkey(*item.keys())[0]
            propertieskey = self.propertieskey(*item.keys())[0]

            if not pathkey or not propertieskey or \
               propertieskey not in item:
                # not enough info
                yield item
                continue

            path = safe_unicode(item[pathkey].lstrip('/')).encode('ascii')
            obj = traverse(self.context, path, None)

            if obj is None:
                # path doesn't exist
                yield item
                continue

            if not getattr(aq_base(obj), '_setProperty', False):
                yield item
                continue

            # Bugfix > Set exclude_from_nav (Plone 5) if excludeFromNav (Plone 4) is True
            try:
              if item['excludeFromNav']:
                  obj.exclude_from_nav = True
            except:
              pass

            # Bugfix > set start & end date in Event object Plone 4 > Plone 5
            # Convert all datetime timezone in UTC+0 to avoid hours change
            try:
                start = item['startDate']
                start = parser.parse(start).replace(tzinfo=pytz.timezone('UTC'))
                end = item['endDate']
                end = parser.parse(end).replace(tzinfo=pytz.timezone('UTC'))
                if start and end:
                    obj.start = start
                    obj.end = end
            except:
                pass

            # Bugfix > Convert Lineage sub site Folder in subsite Dexterity object
            # Need to create a new Dexterity object call Sub Site (sub_site)
            portal_types = self.context.portal_types.listContentTypes()
            if item['_type'] == 'Folder':
                if 'collective.lineage.interfaces.IChildSite' in item['_directly_provided']:

                    dxt_obj_id = 'sub_site'

                    if dxt_obj_id in portal_types:
                        obj.portal_type = dxt_obj_id
                    else:
                        logger.error("Enable to import a Lineage child site. Please add a new Dexterity Folder type with id 'sub_site' and select 1. Folder Addable Constrains 2. Layout support 3. Navigation root in Behavior tab ")
                        raise


            for pid, pvalue, ptype in item[propertieskey]:
                if getattr(aq_base(obj), pid, None) is not None:
                    # if object have a attribute equal to property, do nothing
                    continue

                try:
                    if obj.hasProperty(pid):
                        obj._updateProperty(pid, pvalue)
                    else:
                        obj._setProperty(pid, pvalue, ptype)
                except ConflictError:
                    raise
                except Exception as e:
                    raise Exception('Failed to set property "%s" type "%s"'
                                    ' to "%s" at object %s. ERROR: %s' %
                                    (pid, ptype, pvalue, str(obj), str(e)))

            logger.info("object creation %s" %(obj.absolute_url_path()))

            yield item
