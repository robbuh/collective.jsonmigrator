# -*- coding: utf-8 -*-
from Products.CMFPlone.utils import safe_unicode
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.utils import defaultKeys
from collective.transmogrifier.utils import Matcher
from collective.transmogrifier.utils import traverse
from DateTime import DateTime
from datetime import datetime, timedelta
from Products.Archetypes.interfaces import IBaseObject
from Products.CMFCore.utils import getToolByName
from zope.interface import classProvides
from zope.interface import implements

try:
    from plone.dexterity.interfaces import IDexterityContent
    dexterity_available = True
except:
    dexterity_available = False


class WorkflowHistory(object):

    """
    """

    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.transmogrifier = transmogrifier
        self.name = name
        self.options = options
        self.previous = previous
        self.context = transmogrifier.context
        self.wftool = getToolByName(self.context, 'portal_workflow')

        if 'path-key' in options:
            pathkeys = options['path-key'].splitlines()
        else:
            pathkeys = defaultKeys(options['blueprint'], name, 'path')
        self.pathkey = Matcher(*pathkeys)

        if 'workflowhistory-key' in options:
            workflowhistorykeys = options['workflowhistory-key'].splitlines()
        else:
            workflowhistorykeys = defaultKeys(
                options['blueprint'],
                name,
                'workflow_history')
        self.workflowhistorykey = Matcher(*workflowhistorykeys)

    def __iter__(self):
        for item in self.previous:
            pathkey = self.pathkey(*item.keys())[0]
            workflowhistorykey = self.workflowhistorykey(*item.keys())[0]

            if not pathkey or not workflowhistorykey or \
               workflowhistorykey not in item:  # not enough info
                yield item
                continue

            # traverse() available in version 1.5+ of collective.transmogrifier
            path = safe_unicode(item[pathkey].lstrip('/')).encode('ascii')
            obj = traverse(self.context, path, None)

            if obj is None or not getattr(obj, 'workflow_history', False):
                yield item
                continue


            if (IBaseObject.providedBy(obj) or
                (dexterity_available and IDexterityContent.providedBy(obj))):
                item_tmp = item

                _history = item_tmp.get('_history')

                # get back datetimestamp and set the workflow history
                for workflow in item_tmp[workflowhistorykey]:

                    # Add versions history in workflow
                    if _history:
                      for x in _history:
                          if x['comment']:

                              # Convert _history date from GMT to GMT+1
                              # sort workflow isues see below
                              time = DateTime(x['timestamp']).strftime('%Y/%m/%d %H:%M:%S') # delete GMT declaration
                              time = datetime.strptime(time, '%Y/%m/%d %H:%M:%S') # trasform date in datetime
                              time = time - timedelta(hours=1) # decrease time (1 hour)
                              time = DateTime(time) # convert date in DateTime again

                              item_tmp[workflowhistorykey][workflow].append({'action': x['comment'],
                                                                             'review_state': x['review_state'],
                                                                             'actor': x['principal'],
                                                                             'time': time,
                                                                             })


                    for k, workflow2 in enumerate(item_tmp[workflowhistorykey][workflow]):  # noqa
                        if 'time' in item_tmp[workflowhistorykey][workflow][k]:
                            item_tmp[workflowhistorykey][workflow][k]['time'] = DateTime(  # noqa
                                item_tmp[workflowhistorykey][workflow][k]['time'])  # noqa


                    # Order workflow by time
                    item_tmp[workflowhistorykey][workflow] = sorted(item[workflowhistorykey][workflow], key=lambda k: k['time'])

                # Set workflow
                obj.workflow_history.data = item_tmp[workflowhistorykey]

                # update security
                workflows = self.wftool.getWorkflowsFor(obj)
                if workflows:
                    workflows[0].updateRoleMappingsFor(obj)


            yield item
