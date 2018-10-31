# -*- coding: utf-8 -*-
from Products.CMFPlone.utils import safe_unicode
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.utils import defaultKeys
from collective.transmogrifier.utils import Matcher
from collective.transmogrifier.utils import traverse
from DateTime import DateTime
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
                          if x['comment']: # Should "Initial revision" action be deleted in the _history workflow? Is it useful?

                              # Delete GMT declaration in _history to adjust _history GMT to migration GMT time of object
                              # Added max of millisecond just in case creation object have the same date+hour+minute+second
                              # History always begin after object creation but here we lack of millisecond data in _history workflow
                              time = x['timestamp'][:19]+'.999999'

                              item_tmp[workflowhistorykey][workflow].append({'action': x['comment'],
                                                                             'review_state': x['review_state'],
                                                                             'actor': x['principal'],
                                                                             'time': time,
                                                                             })


                    for k, workflow2 in enumerate(item_tmp[workflowhistorykey][workflow]):  # noqa
                        if 'time' in item_tmp[workflowhistorykey][workflow][k]:
                            item_tmp[workflowhistorykey][workflow][k]['time'] = DateTime(  # noqa
                                item_tmp[workflowhistorykey][workflow][k]['time'])  # noqa


                    # Check if review_state is None, if so, take last valued review_sate il list
                    item_tmp[workflowhistorykey][workflow] = sorted(item[workflowhistorykey][workflow], key=lambda k: k['time'], reverse=True)
                    # search for last valued review_state
                    last_review_state = [x['review_state'] for x in item_tmp[workflowhistorykey][workflow] if x['review_state']][0]
                    for x in item_tmp[workflowhistorykey][workflow]:
                        # set review_state
                        if not x['review_state']:
                            x['review_state'] = last_review_state

                    # Order workflow by time
                    item_tmp[workflowhistorykey][workflow] = sorted(item[workflowhistorykey][workflow], key=lambda k: k['time'])

                # Set workflow
                obj.workflow_history.data = item_tmp[workflowhistorykey]

                # update security
                workflows = self.wftool.getWorkflowsFor(obj)
                if workflows:
                    workflows[0].updateRoleMappingsFor(obj)


            yield item
