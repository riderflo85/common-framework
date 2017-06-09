# coding: utf-8
from collections import OrderedDict

from rest_framework import serializers
from rest_framework.fields import ChoiceField, Field, ReadOnlyField
from rest_framework.relations import HyperlinkedRelatedField, HyperlinkedIdentityField

from common.utils import json_encode, recursive_get_urls


class JsonField(Field):
    """
    JsonField representation for Django REST Framework
    """

    def to_native(self, obj):
        return obj

    def from_native(self, data):
        return json_encode(data, sort_keys=True)

    def to_internal_value(self, data):
        return data

    def to_representation(self, value):
        return value


class QuerySetChoiceField(ChoiceField):
    """
    Surcharge d'un champ de choix se comportant comme une clé étrangère avec l'option de choisir la clé et le libellé
    """
    def __init__(self, model, value=None, label=None, filters=None, order_by=None, **kwargs):
        self.model = model
        self.value = value
        self.label = label
        self.filters = filters
        self.order_by = order_by
        super().__init__(choices=self.values, **kwargs)

    @property
    def values(self):
        try:
            queryset = self.model.objects.filter(**self.filters or {})
            if self.order_by:
                queryset = queryset.order_by(self.order_by)
            return list(queryset.values_list(self.value, self.label))
        except:
            return []


class ChoiceDisplayField(ReadOnlyField):
    """
    Champ pour récupérer la valeur d'une énumération à partir d'un modèle
    """

    def __init__(self, choices, **kwargs):
        self.choices = dict(choices)
        super().__init__(**kwargs)

    def to_representation(self, value):
        return self.choices.get(value)


class ReadOnlyObjectField(ReadOnlyField):
    """
    Surcharge du champ "lecture seule" de DRF pour prendre en compte les objets complets
    """

    def to_representation(self, value):
        if getattr(value, 'url', None):
            url = value.url
            request = self.context.get('request', None)
            if request is not None:
                return request.build_absolute_uri(url)
            return url
        return value.to_dict() if hasattr(value, 'to_dict') else getattr(value, 'id', value)


class CustomHyperlinkedField:
    """
    Surcharge des méthodes pour les champs identifiants par URL
    """
    urls_for_model = {}
    pk_field = None

    def get_name(self, obj):
        # Retourne juste la clé primaire pour éviter de multiplier les requêtes
        return str(obj.pk)

    def get_url(self, obj, view_name, request, format):
        if hasattr(obj, 'pk') and obj.pk in (None, ''):
            return None

        try:
            # Récupération du modèle de la clé étrangère via le modèle du Serializer parent
            model = self.parent.Meta.model._meta.get_field(self.field_name).rel.to
        except:
            # Récupération du modèle lié au QuerySet
            model = getattr(getattr(self, 'queryset', None), 'model', None) or type(obj)

        # Tente de récupérer l'URL dans les APIs qui correspondent exactement au modèle ciblé
        urls = self.urls_for_model[model] = self.urls_for_model.get(model) or list(recursive_get_urls(model=model))
        for urlname, url in urls:
            if urlname.endswith(view_name):
                view_name = urlname

        lookup_value = getattr(obj, self.lookup_field)
        kwargs = {self.lookup_url_kwarg: lookup_value}
        return self.reverse(view_name, kwargs=kwargs, request=request, format=format)


class CustomHyperlinkedIdentityField(CustomHyperlinkedField, HyperlinkedIdentityField):
    """
    Surcharge du champ identifiant par URL pour les clés primaires
    """


class CustomHyperlinkedRelatedField(CustomHyperlinkedField, HyperlinkedRelatedField):
    """
    Surcharge du champ identifiant par URL pour les clés étrangères
    """


class AsymetricRelatedField(serializers.PrimaryKeyRelatedField):
    """
    Surcharge du PrimaryKeyRelatedField permettant la lecture sous forme d'objet serialisé
    et l'écriture sous forme d'ID
    """

    # Constructeur permettant de  générer le field depuis un serializer
    @classmethod
    def from_serializer(cls, serializer, name=None, args=(), kwargs={}):
        if name is None:
            item = serializer.Meta.model if isinstance(serializer, serializers.ModelSerializer) else \
                serializer.__class__
            name = '{}AsymetricAutoField'.format(item.__name__)
        return type(name, (cls,), {"serializer_class": serializer})

    # Surcharge permettant de récupérer l'objet serializé (et non juste l'id)
    def to_representation(self, value):
        return self.serializer_class(value, context=self.context).data

    # Permet de prendre le queryset du model du serializer
    def get_queryset(self):
        if self.queryset:
            return self.queryset
        return self.serializer_class.Meta.model.objects.all()

    # Surcharge retournant directement l'ID de chaque item au lieu de faire appel à 'to_representation'
    # qui ne retourne plus uniquement l'ID, mais un objet serializé
    def get_choices(self, cutoff=None):
        queryset = self.get_queryset()
        if queryset is None:
            return {}

        if cutoff is not None:
            queryset = queryset[:cutoff]

        return OrderedDict([
            (
                item.pk,
                self.display_value(item)
            )
            for item in queryset
        ])
