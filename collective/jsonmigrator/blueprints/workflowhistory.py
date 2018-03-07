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



            # Add versions history in simple_publication_workflow
            _history = item.get('_history')

            if _history:
                for x in _history:
                    if x['comment']:
                        item['_workflow_history']['simple_publication_workflow'].append({'action': x['comment'],
                                                                                         'review_state': x['review_state'],
                                                                                         'actor': x['principal'],
                                                                                         'time': x['timestamp']
                                                                                         })


            if (IBaseObject.providedBy(obj) or
                (dexterity_available and IDexterityContent.providedBy(obj))):
                item_tmp = item

                # Order workflow by time action
                for workflow in item_tmp[workflowhistorykey]:
                    item_tmp[workflowhistorykey][workflow] = sorted(item['_workflow_history']['simple_publication_workflow'], key=lambda k: k['time'])

                # get back datetime stamp and set the workflow history
                for workflow in item_tmp[workflowhistorykey]:
                    for k, workflow2 in enumerate(item_tmp[workflowhistorykey][workflow]):  # noqa
                        if 'time' in item_tmp[workflowhistorykey][workflow][k]:
                            item_tmp[workflowhistorykey][workflow][k]['time'] = DateTime(  # noqa
                                item_tmp[workflowhistorykey][workflow][k]['time'])  # noqa

                obj.workflow_history.data = item_tmp[workflowhistorykey]

                # update security
                workflows = self.wftool.getWorkflowsFor(obj)
                if workflows:
                    workflows[0].updateRoleMappingsFor(obj)


            yield item
