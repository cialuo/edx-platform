"""Models for API management."""
import logging
from smtplib import SMTPException
from urlparse import urlunsplit

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import ugettext as _
from django_extensions.db.models import TimeStampedModel
from edxmako.shortcuts import render_to_string
from simple_history.models import HistoricalRecords

from config_models.models import ConfigurationModel

log = logging.getLogger(__name__)


class ApiAccessRequest(TimeStampedModel):
    """Model to track API access for a user."""

    PENDING = 'pending'
    DENIED = 'denied'
    APPROVED = 'approved'
    STATUS_CHOICES = (
        (PENDING, _('Pending')),
        (DENIED, _('Denied')),
        (APPROVED, _('Approved')),
    )
    user = models.OneToOneField(User)
    status = models.CharField(
        max_length=255,
        choices=STATUS_CHOICES,
        default=PENDING,
        db_index=True,
        help_text=_('Status of this API access request'),
    )
    website = models.URLField(help_text=_('The URL of the website associated with this API user.'))
    reason = models.TextField(help_text=_('The reason this user wants to access the API.'))
    company_name = models.CharField(max_length=255, default='')
    company_address = models.CharField(max_length=255, default='')
    site = models.ForeignKey(Site)
    contacted = models.BooleanField(default=False)

    history = HistoricalRecords()

    @classmethod
    def has_api_access(cls, user):
        """Returns whether or not this user has been granted API access.

        Arguments:
            user (User): The user to check access for.

        Returns:
            bool
        """
        return cls.api_access_status(user) == cls.APPROVED

    @classmethod
    def api_access_status(cls, user):
        """
        Returns the user's API access status, or None if they have not
        requested access.

        Arguments:
            user (User): The user to check access for.

        Returns:
            str or None
        """
        try:
            return cls.objects.get(user=user).status
        except cls.DoesNotExist:
            return None

    def approve(self):
        """Approve this request."""
        log.info('Approving API request from user [%s].', self.user.id)
        self.status = self.APPROVED
        self.save()

    def deny(self):
        """Deny this request."""
        log.info('Denying API request from user [%s].', self.user.id)
        self.status = self.DENIED
        self.save()

    def __unicode__(self):
        return u'ApiAccessRequest {website} [{status}]'.format(website=self.website, status=self.status)


class ApiAccessConfig(ConfigurationModel):
    """Configuration for API management."""

    def __unicode__(self):
        return u'ApiAccessConfig [enabled={}]'.format(self.enabled)


@receiver(post_save, sender=ApiAccessRequest, dispatch_uid="api_access_request_post_save_email")
def send_request_email(sender, instance, created, **kwargs):   # pylint: disable=unused-argument
    """ Send request email after new record created. """
    if created:
        _send_new_pending_email(instance)


@receiver(pre_save, sender=ApiAccessRequest, dispatch_uid="api_access_request_pre_save_email")
def send_decision_email(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """ Send decision email after status changed. """
    if instance.id and not instance.contacted:
        old_instance = ApiAccessRequest.objects.get(pk=instance.id)
        if instance.status != old_instance.status:
            _send_decision_email(instance)


def _send_new_pending_email(instance):
    """ Send an email to settings.API_ACCESS_MANAGER_EMAIL with the contents of this API access request. """
    context = {
        'approval_url': urlunsplit(
            (
                'https' if settings.HTTPS == 'on' else 'http',
                instance.site.domain,
                reverse('admin:api_admin_apiaccessrequest_change', args=(instance.id,)),
                '',
                '',
            )
        ),
        'api_request': instance
    }

    message = render_to_string('api_admin/api_access_request_email_new_request.txt', context)
    try:
        send_mail(
            _('API access request from {company}').format(company=instance.company_name),
            message,
            settings.API_ACCESS_FROM_EMAIL,
            [settings.API_ACCESS_MANAGER_EMAIL],
            fail_silently=False
        )
    except SMTPException:
        log.exception('Error sending API user notification email for request [%s].', instance.id)


def _send_decision_email(instance):
    """ Send an email to requesting user with the decision made about their request. """
    context = {
        'name': instance.user.username,
        'api_management_url': urlunsplit(
            (
                'https' if settings.HTTPS == 'on' else 'http',
                instance.site.domain,
                reverse('api_admin:api-status'),
                '',
                '',
            )
        ),
        'authentication_docs_url': settings.AUTH_DOCUMENTATION_URL,
        'api_docs_url': settings.API_DOCUMENTATION_URL,
        'support_email_address': settings.API_ACCESS_FROM_EMAIL,
        'platform_name': settings.PLATFORM_NAME
    }

    message = render_to_string(
        'api_admin/api_access_request_email_{status}.txt'.format(status=instance.status),
        context
    )
    try:
        send_mail(
            _('API access request'),
            message,
            settings.API_ACCESS_FROM_EMAIL,
            [instance.user.email],
            fail_silently=False
        )
        instance.contacted = True
    except SMTPException:
        log.exception('Error sending API user notification email for request [%s].', instance.id)


class Catalog(models.Model):
    """A (non-Django-managed) model for Catalogs in the course discovery service."""

    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=255, null=False, blank=False)
    query = models.TextField(null=False, blank=False)
    user = models.ForeignKey(User)

    class Meta(object):
        # Catalogs live in course discovery, so we do not create any
        # tables in LMS. Instead we override the save method to post
        # this catalog to discovery.
        managed = False

    def save(self, **kwargs):  # pylint: disable=unused-argument
        # TODO: save this catalog to discovery
        return None

    @classmethod
    def all(cls):
        """
        TODO: get these from the course discovery service. This method is
        just for testing right now.
        """
        return [
            Catalog(id=i, name='test_' + str(i), query='*') for i in xrange(5)
        ]

    def __unicode__(self):
        return u'Catalog {name} {query}'.format(name=self.name, query=self.query)
