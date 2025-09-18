#!/usr/bin/env python3
"""Minimal Netcup Mailserver SOAP client helpers."""
from __future__ import annotations
import os
from typing import Optional

from zeep import Client
from zeep.transports import Transport

MAILSERVER_WSDL = os.getenv("NETCUP_MAIL_WSDL", "https://ccp.netcup.net/wsdl/mailserver.wsdl")

class NetcupMailClient:
    def __init__(self, customer_number: str, api_key: str, api_password: str):
        transport = Transport(timeout=30)
        self.client = Client(MAILSERVER_WSDL, transport=transport)
        self.customer_number = customer_number
        self.api_key = api_key
        self.api_password = api_password
        self.session_id: Optional[str] = None
        self.api_session_id: Optional[str] = None

    def login(self) -> None:
        resp = self.client.service.login(
            customerNumber=self.customer_number,
            apiKey=self.api_key,
            apiPassword=self.api_password,
        )
        try:
            self.session_id = resp["sessionid"]
            self.api_session_id = resp["apisessionid"]
        except (TypeError, KeyError):
            self.session_id = getattr(resp, "sessionid", None)
            self.api_session_id = getattr(resp, "apisessionid", None)

    def logout(self) -> None:
        if self.session_id and self.api_session_id:
            self.client.service.logout(
                customerNumber=self.customer_number,
                apiKey=self.api_key,
                sessionId=self.session_id,
                apisessionid=self.api_session_id,
            )

    def create_mailbox(self, domain: str, username: str, password: str, quota_mb: int, firstname: str = "", lastname: str = "") -> dict:
        if not self.session_id:
            raise RuntimeError("login first")
        mailbox = self.client.get_type('ns0:mailaccount_typ')(
            mailaccount=username,
            domainname=domain,
            password=password,
            quota=quota_mb,
            autoresponder=0,
            redirect='',
            forwarders='',
            firstname=firstname,
            lastname=lastname,
        )
        return self.client.service.mailaccount_add(
            customerNumber=self.customer_number,
            apiKey=self.api_key,
            sessionId=self.session_id,
            apisessionid=self.api_session_id,
            mailaccount=mailbox,
        )
