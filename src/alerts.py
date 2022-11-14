from os import environ
environ["PRODUCTION"] = environ["PRODUCTION"] if "PRODUCTION" in environ and environ["PRODUCTION"] else ""

from signal import signal, SIGINT, SIGTERM
from time import time, sleep
from datetime import datetime
from aiohttp import TCPConnector, ClientSession
from asyncio import wait, run, create_task
from orjson import dumps, OPT_SORT_KEYS
from uuid import uuid4
from pytz import utc
from traceback import format_exc

from google.cloud.firestore import AsyncClient as FirestoreClient
from google.cloud.error_reporting import Client as ErrorReportingClient

from DatabaseConnector import DatabaseConnector
from helpers.utils import seconds_until_cycle, get_accepted_timeframes


database = FirestoreClient()


class AlertsServer(object):
	accountProperties = DatabaseConnector(mode="account")
	registeredAccounts = {}


	# -------------------------
	# Startup
	# -------------------------
	
	def __init__(self):
		self.isServiceAvailable = True
		signal(SIGINT, self.exit_gracefully)
		signal(SIGTERM, self.exit_gracefully)

		self.logging = ErrorReportingClient(service="alerts")

		self.url = "http://candle-server:6900/candle/" if environ['PRODUCTION'] else "http://candle-server:6900/candle/"

	def exit_gracefully(self, signum, frame):
		print("[Startup]: Alerts Server handler is exiting")
		self.isServiceAvailable = False


	# -------------------------
	# Job queue
	# -------------------------

	async def run(self):
		while self.isServiceAvailable:
			try:
				sleep(seconds_until_cycle())
				t = datetime.now().astimezone(utc)
				timeframes = get_accepted_timeframes(t)

				if "1m" in timeframes:
					await self.update_accounts()
					await self.process_price_alerts()

			except (KeyboardInterrupt, SystemExit): return
			except Exception:
				print(format_exc())
				if environ["PRODUCTION"]: self.logging.report_exception()

	async def update_accounts(self):
		try:
			self.registeredAccounts = await self.accountProperties.keys()
		except (KeyboardInterrupt, SystemExit): pass
		except Exception:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception()


	# -------------------------
	# Price Alerts
	# -------------------------

	async def process_price_alerts(self):
		startTimestamp = time()
		conn = TCPConnector(limit=5)
		async with ClientSession(connector=conn) as session:
			try:
				requestMap = {}
				alerts = []
				users = database.document("details/marketAlerts").collections()
				async for user in users:
					accountId = user.id
					if not environ["PRODUCTION"] and accountId != "ebOX1w1N2DgMtXVN978fnL0FKCP2": continue
					authorId = accountId if accountId.isdigit() else self.registeredAccounts.get(accountId)
					if authorId is None: continue
					async for alert in user.stream():
						key = dumps(alert.to_dict()["request"]["ticker"], option=OPT_SORT_KEYS)
						if key in requestMap:
							requestMap[key][1].append(len(alerts))
						else:
							requestMap[key] = [
								create_task(self.fetch_candles(session, authorId, alert.to_dict())),
								[len(alerts)]
							]
						alerts.append((authorId, accountId, alert))

				tasks = []
				for key, [request, indices] in requestMap.items():
					payload = await request
					if payload is None: continue
					for i in indices:
						(authorId, accountId, alert) = alerts[i]
						tasks.append(create_task(self.check_price_alert(payload, authorId, accountId, alert.reference, alert.to_dict())))
				if len(tasks) > 0: await wait(tasks)

				print("Task finished in", time() - startTimestamp, "seconds")
			except (KeyboardInterrupt, SystemExit): pass
			except Exception:
				print(format_exc())
				if environ["PRODUCTION"]: self.logging.report_exception()

	async def fetch_candles(self, session, authorId, alert):
		try:
			payload, message = {}, ""
			async with session.post(self.url + alert["currentPlatform"].lower(), json=alert["request"]) as response:
				data = await response.json()
				payload, message = data.get("response"), data.get("message")

			if not bool(payload):
				if message is not None:
					print("Alert request error:", message)
					if environ["PRODUCTION"]: self.logging.report(message)
				return
			return payload
		except:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception()
			return { "candles": [] }

	async def check_price_alert(self, payload, authorId, accountId, reference, alert):
		try:
			ticker = alert["request"].get("ticker")
			exchangeName = f" ({ticker.get('exchange').get('name')})" if ticker.get("exchange") else ''

			if alert["timestamp"] < time() - 86400 * 30.5 * 3:
				if environ["PRODUCTION"]:
					await database.document(f"discord/properties/messages/{str(uuid4())}").set({
						"title": f"Price alert for {ticker.get('name')}{exchangeName} at {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')} expired.",
						"subtitle": "Price Alerts",
						"description": "Price alerts automatically cancel after 3 months. If you'd like to keep your alert, you'll have to schedule it again.",
						"color": 6765239,
						"user": authorId,
						"channel": alert.get("channel"),
						"backupUser": authorId,
						"backupChannel": alert.get("backupChannel")
					})
					await reference.delete()

				else:
					print(f"{accountId}: price alert for {ticker.get('name')}{exchangeName} at {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')} expired")

			else:
				for candle in reversed(payload["candles"]):
					if candle[0] < alert["timestamp"]: break
					if (alert["placement"] == "below" and candle[3] is not None and candle[3] <= alert["level"]) or (alert["placement"] == "above" and candle[2] is not None and alert["level"] <= candle[2]):
						if environ["PRODUCTION"]:
							await database.document(f"discord/properties/messages/{str(uuid4())}").set({
								"title": f"Price of {ticker.get('name')}{exchangeName} hit {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')}.",
								"description": alert.get("triggerMessage"),
								"tag": alert.get("triggerTag"),
								"subtitle": "Price Alerts",
								"color": 6765239,
								"user": authorId if alert["channel"] is None else None,
								"channel": alert.get("channel"),
								"backupUser": authorId,
								"backupChannel": alert.get("backupChannel")
							})
							await reference.delete()

						else:
							print(f"{accountId}: price of {ticker.get('name')}{exchangeName} hit {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')}")
						break

		except (KeyboardInterrupt, SystemExit): pass
		except Exception:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception(user=f"{accountId}, {authorId}")


if __name__ == "__main__":
	alertsServer = AlertsServer()
	run(alertsServer.run())