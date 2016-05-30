""" This module contains classes and logic to handle operations on records
"""

from ..utils import (wpartial,
                     normalizeSField,
                     preprocess_args,
                     ustr,
                     DirMixIn)
from .object import Object
from .cache import (empty_cache,
                    Cache)


import six
import abc
import numbers
import functools
import collections
from extend_me import (ExtensibleType,
                       ExtensibleByHashType)


__all__ = (
    'Record',
    'RecordRelations',
    'ObjectRecords',
    'RecordList',
    'get_record',
    'get_record_list',
)


RecordMeta = ExtensibleByHashType._('Record', hashattr='object_name')


def get_record(obj, rid, cache=None, context=None):
    """ Creates new Record instance

        Use this method to create new records, because of standard
        object creation bypasses extension's magic.

            :param Object obj: instance of Object this record is related to
            :param int rid: ID of database record to fetch data from
            :param cache: Cache instance. (usualy generated by
                          function empty_cache()
            :type cache: Cache
            :param dict context: if specified, then cache's context
                                 will be updated
            :return: created Record instance
            :rtype: Record
    """
    cls = RecordMeta.get_class(obj.name, default=True)
    return cls(obj, rid, cache=cache, context=context)


@six.python_2_unicode_compatible
class Record(six.with_metaclass(RecordMeta, DirMixIn)):
    """ Base class for all Records

        Do not use it to create record instances manualy.
        Use ``get_record`` function instead.
        It implements all extensions mangic

        But class should be used for ``isinstance`` checks.

        It is posible to create extensions of this class that will be binded
        only to specific Odoo objects

        For example, if You need to extend all recrods of products,
        do something like this::

            class MyProductRecord(Record):
                class Meta:
                    object_name = 'product.product'

                def __init__(self, *args, **kwargs):
                    super(MyProductRecord, self).__init__(*args, **kwargs)

                    # to avoid double read, save once read value to record
                    # instance
                    self._sale_orders = None

                @property
                def sale_orders(self):
                    ''' Sale orders related to curent product
                    '''
                    if self._sale_orders is None:
                        so = self._client['sale.order']
                        domain = [('order_line.product_id', '=', self.id)]
                        self._sale_orders = so.search_records(
                                                domain, cache=self._cache)
                    return self._sale_orders

        And atfter this, next code is valid::

            products = client['product.product'].search_records([])
            products_so = products.filter(lambda p: bool(p.sale_orders))
            products_so_gt_10 = products.filter(
                lambda p: len(p.sale_orders) > 10)

            for product in products_so_gt_10:
                print("Product: %s" % product.default_code)
                for pso in product.sale_orders:
                    print("\t%s" % pso.name)


        :param Object obj: instance of object this record is related to
        :param int rid: ID of database record to fetch data from
        :param cache: Cache instance.
                      (usualy generated by function empty_cache()
        :type cache: Cache
        :param dict context: if specified, then cache's context
                             will be updated

        Note, to create instance of cache call *empty_cache*
    """

    __slots__ = ['_object', '_cache', '_lcache', '_id', '_related_objects']

    def __init__(self, obj, rid, cache=None, context=None):
        assert isinstance(obj, Object), "obj should be Object"
        assert isinstance(rid, numbers.Integral), "rid must be int"

        self._id = rid
        self._object = obj
        self._cache = empty_cache(obj.client) if cache is None else cache
        self._lcache = self._cache[obj.name]
        self._related_objects = {}

        self._lcache[self._id]  # ensure that ID of this record is in cache.
        if context is not None:
            self._lcache.update_context(context)

    def __dir__(self):
        res = super(Record, self).__dir__()
        res.extend(self._columns_info.keys())
        res.extend(self._object.stdcall_methods)
        return list(set(res))

    @property
    def id(self):
        """ Record ID
        """
        return self._id

    @property
    def _data(self):
        """ Data dictionary for this record.
            (Just a client to cache)
        """
        return self._lcache[self._id]

    @property
    def context(self):
        """ Returns context to be used for thist record
        """
        return self._lcache.context

    @property
    def _service(self):
        """ Returns instance of related Object service instance
        """
        return self._object.service

    @property
    def _client(self):
        """ Returns instance of related Client object
        """
        return self._object.client

    @property
    def _columns_info(self):
        """ Returns dictionary with information about columns of related object
        """
        return self._object.columns_info

    @property
    def as_dict(self):
        """ Provides dictionary with record's data in raw form
        """
        return self._data.copy()

    @property
    def _name(self):
        """ Returns result of name_get for this record
        """
        if self._data.get('__name_get_result', None) is None:
            lcache = self._lcache
            data = self._object.name_get(list(lcache), context=self.context)
            for _id, name in data:
                lcache[_id]['__name_get_result'] = name
        return self._data.get('__name_get_result', u'ERROR')

    def __str__(self):
        return u"R(%s, %s)[%s]" % (self._object.name,
                                   self.id,
                                   ustr(self._name))

    def __repr__(self):
        return str(self)

    def __int__(self):
        return self._id

    def __hash__(self):
        return hash((self._object.name, self._id))

    def __eq__(self, other):
        if isinstance(other, Record):
            return other.id == self._id

        if isinstance(other, numbers.Integral):
            return self._id == other

        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def _get_many2one_rel_obj(self, name, rel_data, cached=True):
        """ Method used to fetch related object by name of field
            that points to it
        """
        if name not in self._related_objects or not cached:
            if rel_data:
                # Do not forged about relations in form [id, name]
                rel_id = (rel_data[0]
                          if isinstance(rel_data, collections.Iterable)
                          else rel_data)

                rel_obj = self._service.get_obj(
                    self._columns_info[name]['relation'])
                self._related_objects[name] = get_record(rel_obj,
                                                         rel_id,
                                                         cache=self._cache,
                                                         context=self.context)
            else:
                self._related_objects[name] = False
        return self._related_objects[name]

    def _get_one2many_rel_obj(self, name, rel_ids, cached=True, limit=None):
        """ Method used to fetch related objects by name of field
            that points to them using one2many relation
        """
        if name not in self._related_objects or not cached:
            rel_obj = self._service.get_obj(
                self._columns_info[name]['relation'])
            self._related_objects[name] = get_record_list(rel_obj,
                                                          rel_ids,
                                                          cache=self._cache,
                                                          context=self.context)
        return self._related_objects[name]

    def _get_field(self, ftype, name):
        """ Returns value for field 'name' of type 'type'

            :param str ftype: type of field to det value for
            :param str name: name of field to read

            Should be overridden by extensions to provide better hadling
            for diferent field values
        """
        if name not in self._data:
            # save 'cache_field' function before for loop
            cache_field = self._lcache.cache_field

            # get list of ids in cache, that have not read requested field
            for data in self._object.read(self._lcache.get_ids_to_read(name),
                                          [name],
                                          context=self.context):
                # write each row of data to cache
                cache_field(data['id'], ftype, name, data[name])

        # relational fields
        if ftype == 'many2one':
            return self._get_many2one_rel_obj(name, self._data[name])
        if ftype in ('one2many', 'many2many'):
            return self._get_one2many_rel_obj(name, self._data[name])

        return self._data[name]

    # Allow dictionary access to data fields
    def __getitem__(self, name):
        if name == 'id':
            return self.id

        field = self._columns_info.get(name, None)

        if field is None:
            raise KeyError("No such field %s in object %s, %s"
                           "" % (name, self._object.name, self.id))

        ftype = field and field['type']

        # TODO: refactore to be able to pass field instead of only field type
        return self._get_field(ftype, name)

    # Allow to access data as attributes and call object's methods
    # directly from record object
    def __getattr__(self, name):
        try:
            res = self[name]   # Try to get data field
        except KeyError:
            method = getattr(self._object, name)
            res = wpartial(method, [self.id])
            setattr(self, name, res)
        return res

    def refresh(self):
        """Reread data and clean-up the caches

           :returns: self
           :rtype: Record
        """
        self._data.clear()
        self._data['id'] = self._id

        # Update related objects cache
        rel_objects = self._related_objects
        self._related_objects = {}  # cleanup related_objects cache

        # recursively cleanup related records
        for rel in rel_objects.values():
            if isinstance(rel, (Record, RecordList)):
                # both, Record and RecordList objects have *refresh* method
                rel.refresh()

        return self

    def read(self, fields=None, context=None, multi=False):
        """ Rereads data for this record (or for al records in whole cache)

            :param list fields: list of fields to be read (optional)
            :param dict context: context to be passed to read (optional)
                                 does not midify record's context
            :param bool multi: if set to True, that data will be read for
                               all records of this object in current
                               cache (query).
            :return: dict with data had been read
            :rtype: dict
        """
        ctx = {} if self.context is None else self.context.copy()
        if context is not None:
            ctx.update(context)

        ids = list(self._lcache) if multi else [self.id]
        args, kwargs = preprocess_args(ids, fields, context=ctx or None)

        res = {}
        for rdata in self._object.read(*args, **kwargs):
            self._lcache[rdata['id']].update(rdata)
            if rdata['id'] == self.id:
                res = rdata
        return res

    def copy(self, default=None, context=None):
        """ copy this record.

            :param dict default: dictionary default values for new record
                                 (optional)
            :param dict context: dictionary with context used to copy
                                 this record. (optional)
            :return: Record instance for created record
            :rtype: Record

            Note about context: by default cache's context will be used,
            and if some context will be passed to this method, new dict,
            which is combination of default context and passed context,
            will be passed to server.
        """
        ctx = {} if self.context is None else self.context.copy()

        if context is not None:
            ctx.update(context)

        # None values should not be passed via xml-rpc
        args, kwargs = preprocess_args(self.id,
                                       default=default,
                                       context=ctx or None)

        new_id = self._object.copy(*args, **kwargs)
        return get_record(self._object,
                          new_id,
                          cache=self._cache,
                          context=self.context)


RecordListMeta = ExtensibleType._('RecordList', with_meta=abc.ABCMeta)


def get_record_list(obj, ids=None, fields=None, cache=None, context=None):
    """ Returns new instance of RecordList object.

        :param obj: instance of Object to make this list related to
        :type obj: Object
        :param ids: list of IDs of objects to read data from
        :type ids: list of int
        :param fields: list of field names to read by default  (not used now)
        :type fields: list of strings (not used now)
        :param cache: Cache instance.
                      (usualy generated by function empty_cache()
        :type cache: Cache
        :param context: context to be passed automatically to methods
                        called from this list (not used yet)
        :type context: dict
    """
    return RecordListMeta.get_object(obj,
                                     ids,
                                     fields=fields,
                                     cache=cache,
                                     context=context)


@six.python_2_unicode_compatible
class RecordList(six.with_metaclass(RecordListMeta,
                                    collections.MutableSequence,
                                    DirMixIn)):
    """Class to hold list of records with some extra functionality

        :param obj: instance of Object to make this list related to
        :type obj: Object
        :param ids: list of IDs of objects to read data from
        :type ids: list of int
        :param fields: list of field names to read by default
        :type fields: list of strings
        :param cache: Cache instance.
                      (usualy generated by function empty_cache()
        :type cache: Cache
        :param context: context to be passed automatically to methods
                        called from this list (not used yet)
        :type context: dict

    """
    __slots__ = ('_object', '_cache', '_lcache', '_records')

    # TODO: expose object's methods via implementation of __dir__

    def __init__(self, obj, ids=None, fields=None, cache=None, context=None):
        """
        """
        self._object = obj
        self._cache = empty_cache(obj.client) if cache is None else cache
        self._lcache = self._cache[obj.name]

        if context is not None:
            self._lcache.update_context(context)

        ids = [] if ids is None else ids

        # We need to add these ids to cache to make prefetching and data
        # reading work correctly. if some of ids will not be present in cache,
        # then, on access to field of record with such id, data will not be
        # read from database.
        # Look into *Record._get_field* method for more info
        self._lcache.update_keys(ids)

        _cache = self._cache  # before loop, save cache in separate variable
        self._records = [get_record(obj, id_, cache=_cache)
                         for id_ in ids]

        # if there some fields prefetching was requested, do it
        if fields is not None:
            self.prefetch(*fields)

    def __dir__(self):
        res = super(RecordList, self).__dir__()
        res.extend(self._object.stdcall_methods)
        return list(set(res))

    @property
    def object(self):
        """ Object this record is related to
        """
        return self._object

    @property
    def context(self):
        """ Returns context to be used for this list
        """
        return self._lcache.context

    @property
    def ids(self):
        """ IDs of records present in this RecordList
        """
        return [r.id for r in self._records]

    @property
    def records(self):
        """ Returns list (class 'list') of records
        """
        return self._records

    @property
    def length(self):
        """ Returns length of this record list
        """
        return len(self._records)

    def _new_context(self, new_context=None):
        """ Create new context which is combination of *self.context*
            and passed context argument.

            mostly for internal usage

            :param dict new_context: new context. default is None
            :return: new context dict which is combination of
                     *self.context* and *new_context* or *None*
            :rtype: dict|None
        """
        if new_context is None:
            return self.context

        ctx = {} if self.context is None else self.context.copy()
        ctx.update(new_context)
        return ctx

    # Container related methods
    def __getitem__(self, index):
        if isinstance(index, slice):
            # Note no context passed, because it is stored in cache
            return get_record_list(self.object,
                                   ids=[r.id for r in self._records[index]],
                                   cache=self._cache)
        return self._records[index]

    def __setitem__(self, index, value):
        if isinstance(value, Record):
            self._records[index] = value
        else:
            raise ValueError("In 'RecordList[index] = value' operation, "
                             "value must be instance of Record")

    def __delitem__(self, index):
        del self._records[index]

    def __iter__(self):
        return iter(self._records)

    def __len__(self):
        return self.length

    def __contains__(self, item):
        if isinstance(item, numbers.Integral):
            return item in self.ids
        if isinstance(item, Record):
            return item in self._records
        return False

    def insert(self, index, item):
        """ Insert record to list

            :param item: Record instance to be inserted into list.
                         if int passed, it considered to be ID of record
            :type item: Record|int
            :param int index: position where to place new element
            :return: self
            :rtype: RecordList
        """
        assert isinstance(item, (Record, numbers.Integral)), \
            "Only Record or int instances could be added to list"
        if isinstance(item, Record):
            self._records.insert(index, item)
        else:
            self._records.insert(index, self._object.read_records(item))
        return self

    # Overridden to make ability to call methods of object on list of IDs
    # present in this RecordList
    def __getattr__(self, name):
        method = getattr(self.object, name)
        kwargs = {} if self.context is None else {'context': self.context}
        res = wpartial(method, self.ids, **kwargs)
        return res

    def __str__(self):
        return u"RecordList(%s): length=%s" % (self.object.name, self.length)

    def __repr__(self):
        return str(self)

    def refresh(self):
        """ Cleanup data caches. next try to get data will cause rereading of it

           :returns: self
           :rtype: instance of RecordList
        """
        for record in self.records:
            record.refresh()
        return self

    def sort(self, key=None, reverse=False):
        """ sort(key=None, reverse=False) -- inplace sort

            anyfield.SField instances may be safely passed as 'key' arguments.
            no need to convert them to function explicitly

            :return: self
        """
        if callable(key):
            key = normalizeSField(key)

        self._records.sort(key=key, reverse=reverse)
        return self

    def group_by(self, grouper):
        """ Groups all records in list by specifed grouper.

            :param grouper: field name or callable to group results by.
                            if callable is passed, it should receive only
                            one argument - record instance, and result of
                            calling grouper will be used as key
                            to group records by.
            :type grouper: string|callable(record)|anyfield.SField
            :return: dictionary

            for example we have list of sale orders and
            want to group it by state

            .. code-block:: python

              # so_list - variable that contains list of sale orders selected
              # by some criterias. so to group it by state we will do:
              group = so_list.group_by('state')

              # Iterate over resulting dictionary
              for state, rlist in group.iteritems():
                  # Print state and amount of items with such state
                  print state, rlist.length

            or imagine that we would like to group records
            by last letter of sale order number

            .. code-block:: python

              # so_list - variable that contains list of sale orders selected
              # by some criterias. so to group it by last letter of sale
              # order name  we will do:
              group = so_list.group_by(lambda so: so.name[-1])

              # Iterate over resulting dictionary
              for letter, rlist in group.iteritems():
                  # Print state and amount of items with such state
                  print letter, rlist.length

        """
        if callable(grouper):
            grouper = normalizeSField(grouper)

        cls_init = functools.partial(get_record_list,
                                     self.object,
                                     ids=[],
                                     cache=self._cache)
        res = collections.defaultdict(cls_init)
        for record in self.records:
            if isinstance(grouper, six.string_types):
                key = record[grouper]
            elif callable(grouper):
                key = grouper(record)

            res[key].append(record)
        return res

    def filter(self, func):
        """ Filters items using *func*.

            :param func: callable to check if record should be included
                         in result.
            :type func: callable(record)->bool|anyfield.SField
            :return: RecordList which contains records that matches results
            :rtype: RecordList
        """
        func = normalizeSField(func)
        return get_record_list(self.object,
                               ids=[r.id for r in self.records if func(r)],
                               cache=self._cache)

    def mapped(self, field):
        """ **Experimental**, Provides similar functionality
            to Odoo's mapped() method, but supports only dot-separated
            field name as argument, no callables yet.

            Returns list of values of field of each record in this recordlist.
            If value of field is RecordList or Record instance,
            than RecordList instance will be returned

            Thus folowing code will work

            .. code:: python

                # returns a list of names
                records.mapped('name')

                # returns a recordset of partners
                record.mapped('partner_id')

                # returns the union of all partner banks,
                # with duplicates removed
                record.mapped('partner_id.bank_ids')

            :param str field: returns list of values of 'field'
                              for each record in this RecordList
            :rtype: list or RecordList
        """
        def get_field(rec):
            fields = field.split('.')
            val = rec
            while fields and val:
                f = fields.pop(0)
                val = val[f]

            return val

        # Choose type of result
        (res_model,
         res_field,
         res_rel_model) = self._object.resolve_field_path(field)[-1]
        if res_rel_model:
            res_obj = self._object.client[res_rel_model]
            res = get_record_list(res_obj,
                                  [],
                                  cache=self._cache,
                                  context=self.context)
        else:
            res = []

        for record in self.records:
            val = get_field(record)
            if not val:
                continue

            if isinstance(val, RecordList):
                res.extend(val)
            elif val not in res:
                res.append(val)

        return res

    def copy(self, context=None, new_cache=False):
        """ Returns copy of this list, possibly with modified context
            and new empty cache.

            :param dict context: new context values to be used on new list
            :param true new_cache: if set to True, then new cache instance
                                   will be created for resulting recordlist
                                   if set to Cache instance, than it will be
                                   used for resulting recordlist
            :return: copy of this record list.
            :rtype: RecordList
            :raises ValueError: when incorrect value passed to new_cache
        """
        if isinstance(new_cache, Cache):
            cache = new_cache
        elif not new_cache:
            cache = self._cache
        elif new_cache is True:
            cache = empty_cache(self.object.client)
        else:
            raise ValueError("Wrong value for parametr 'new_cache': %r"
                             "" % (new_cache,))

        return get_record_list(self.object,
                               ids=self.ids,
                               cache=cache,
                               context=context)

    def existing(self, uniqify=True):
        """ Filters this list with only existing items

            :parm bool uniqify: if set to True, then all dublicates
                                will be removed. Default: True
            :return: new RecordList instance
            :rtype: RecordList
        """
        existing_ids = self.exists()
        new_ids = []
        for id_ in self.ids:
            if id_ not in existing_ids:
                continue
            if uniqify and id_ in new_ids:
                continue
            new_ids.append(id_)
        return get_record_list(self.object,
                               ids=new_ids,
                               cache=self._cache)

    def prefetch(self, *fields):
        """ Prefetches specified fields into cache
            if no fields passed, then all 'simple_fields' will be prefetched

            By default field read performed only when that field is requested,
            thus when You need to read more then one field, few rpc requests
            will be performed. to avoid multiple unneccessary rpc calls this
            method is implemented.

            :return: self, which allows chaining of operations
            :rtype: RecordList
        """
        fields = fields if fields else self.object.simple_fields

        self._lcache.prefetch_fields(fields)

        return self

    # remote method overrides
    def search(self, domain, *args, **kwargs):
        """ Performs normal search, but adds ``('id', 'in', self.ids)``
            to search domain

            :returns: list of IDs found
            :rtype: list of integers
        """
        ctx = self._new_context(kwargs.get('context', None))

        if ctx is not None:
            kwargs['context'] = ctx

        return self.object.search([('id', 'in', self.ids)] + domain,
                                  *args,
                                  **kwargs)

    def search_records(self, domain, *args, **kwargs):
        """ Performs normal search_records, but adds
            ``('id', 'in', self.ids)`` to domain

            :returns: RecordList of records found
            :rtype: RecordList instance
        """
        ctx = self._new_context(kwargs.get('context', None))

        if ctx is not None:
            kwargs['context'] = ctx

        return self.object.search_records([('id', 'in', self.ids)] + domain,
                                          *args,
                                          **kwargs)

    def read(self, fields=None, context=None):
        """ Read wrapper. Takes care about adding RecordList's context to
            object's read method.

            **Warning**: does not update cache by data been read
        """
        ctx = self._new_context(context)
        args, kwargs = preprocess_args(fields, context=ctx)
        return self.object.read(self.ids, *args, **kwargs)


# For backward compatability
RecordRelations = Record


class ObjectRecords(Object):
    """ Adds support to use records from Object classes
    """

    def __init__(self, *args, **kwargs):
        super(ObjectRecords, self).__init__(*args, **kwargs)
        self._model = None

    @property
    def model(self):
        """ Returns Record instance of model related to this object.
            Useful to get additional info on object.
        """
        if self._model is None:
            model_obj = self.client.get_obj('ir.model')
            res = model_obj.search_records([('model', '=', self.name)],
                                           limit=2)
            assert res.length == 1, \
                "There must be only one model for this name"
            self._model = res[0]

        return self._model

    @property
    def model_name(self):
        """ Result of name_get called on object's model
        """
        return self.model._name

    @property
    def simple_fields(self):
        """ List of simple fields which could be fetched fast enough

            This list contains all fields that are not function nor binary

            :type: list of strings
        """
        return [f for f, d in six.iteritems(self.columns_info)
                if d['type'] != 'binary' and not d.get('function', False)]

    def search_records(self, *args, **kwargs):
        """ Return instance or list of instances of Record class,
            making available to work with data simpler

            :param domain: list of tuples, specifying search domain
            :param int offset: (optional) number of results to skip
                               in the returned values
                               (default:0)
            :param limit: optional max number of records  in result
                          (default: False)
            :type limit: int|False
            :param order: optional columns to sort
            :type order: str
            :param dict context: optional context to pass to *search* method
            :param count: if set to True, then only amount of recrods found
                          will be returned.
                          (default: False)
            :param read_fields: optional. specifies list of fields to read.
            :type read_fields: list of strings
            :param Cache cache: cache to be used for records and recordlists
            :return: RecordList contains records found, or integer
                     that represents amount of records found (if count=True)
            :rtype: RecordList|int

            For example:

            .. code:: python

                >>> so_obj = db['sale.order']
                >>> data = so_obj.search_records([('date','>=','2013-01-01')])
                >>> for order in data:
                ...     order.write({'note': 'order date is %s'%order.date})
        """

        # TODO: use search_read for odoo versions >= 8.0
        read_fields = kwargs.pop('read_fields', None)
        context = kwargs.get('context', None)
        cache = kwargs.pop('cache', None)

        if kwargs.get('count', False):
            return self.search(*args, **kwargs)

        res = self.search(*args, **kwargs)
        if not res:
            return get_record_list(self,
                                   ids=[],
                                   fields=read_fields,
                                   context=context,
                                   cache=cache)

        if read_fields:
            return self.read_records(res,
                                     read_fields,
                                     context=context,
                                     cache=cache)
        return self.read_records(res, context=context, cache=cache)

    def read_records(self, ids, fields=None, context=None, cache=None):
        """ Return instance or RecordList class,
            making available to work with data simpler

            :param ids: ID or list of IDS to read data for
            :type ids: int|list of int
            :param list fields: list of fields to read (*optional*)
            :param dict context: context to be passed to read. default=None
            :param Cache cache: cache to use for records and record lists.
                          Pass None to create new cache. default=None.
            :return: Record instance if *ids* is int or RecordList instance
                     if *ids* is list of ints
            :rtype: Record|RecordList

            For example:

            .. code:: python

                >>> so_obj = db['sale.order']
                >>> data = so_obj.read_records([1,2,3,4,5])
                >>> for order in data:
                        order.write({'note': 'order data is %s'%order.data})
        """
        if isinstance(ids, numbers.Integral):
            record = get_record(self, ids, context=context)
            if fields is not None:
                record.read(fields)  # read specified fields
            return record
        if isinstance(ids, collections.Iterable):
            return get_record_list(self, ids, fields=fields, context=context)

        raise ValueError("Wrong type for ids argument: %s" % type(ids))

    def browse(self, *args, **kwargs):
        """ Aliase to *read_records* method.
            In most cases same as serverside *browse*
            (i mean server version 7.0)
        """
        return self.read_records(*args, **kwargs)
