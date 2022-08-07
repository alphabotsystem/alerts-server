from os import environ
from signal import signal, SIGINT, SIGTERM
from time import time, sleep
from datetime import datetime
import aiohttp
from asyncio import wait, run, create_task
from uuid import uuid4
from pytz import utc
from traceback import format_exc

import google.auth.transport.requests
import google.oauth2.id_token
from google.cloud.firestore import AsyncClient as FirestoreClient
from google.cloud.error_reporting import Client as ErrorReportingClient

from DatabaseConnector import DatabaseConnector
from helpers.utils import Utils


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

		self.url = "https://candle-server-yzrdox65bq-uc.a.run.app/" if environ['PRODUCTION_MODE'] else "http://candle-server:6900/"

	def exit_gracefully(self, signum, frame):
		print("[Startup]: Alerts Server handler is exiting")
		self.isServiceAvailable = False


	# -------------------------
	# Job queue
	# -------------------------

	async def run(self):
		while self.isServiceAvailable:
			try:
				sleep(Utils.seconds_until_cycle())
				t = datetime.now().astimezone(utc)
				timeframes = Utils.get_accepted_timeframes(t)

				if "1m" in timeframes:
					await self.update_accounts()
					await self.process_price_alerts()

			except (KeyboardInterrupt, SystemExit): return
			except Exception:
				print(format_exc())
				if environ["PRODUCTION_MODE"]: self.logging.report_exception()

	async def update_accounts(self):
		try:
			self.registeredAccounts = await self.accountProperties.keys()
		except (KeyboardInterrupt, SystemExit): pass
		except Exception:
			print(format_exc())
			if environ["PRODUCTION_MODE"]: self.logging.report_exception()


	# -------------------------
	# Price Alerts
	# -------------------------

	async def process_price_alerts(self):
		auth_req = google.auth.transport.requests.Request()
		token = google.oauth2.id_token.fetch_id_token(auth_req, "https://candle-server-yzrdox65bq-uc.a.run.app/")
		headers = {
			"Authorization": "Bearer " + token,
			"content-type": "application/json",
			"accept": "application/json"
		}
		async with aiohttp.ClientSession(headers=headers) as session:
			tasks = []
			try:
				users = database.document("details/marketAlerts").collections()
				async for user in users:
					accountId = user.id
					if not environ["PRODUCTION_MODE"] and accountId != "ebOX1w1N2DgMtXVN978fnL0FKCP2": continue
					authorId = accountId if accountId.isdigit() else self.registeredAccounts.get(accountId)
					if authorId is None: continue
					async for alert in user.stream():
						tasks.append(create_task(self.check_price_alert(session, authorId, accountId, alert.reference, alert.to_dict())))

			except (KeyboardInterrupt, SystemExit): pass
			except Exception:
				print(format_exc())
				if environ["PRODUCTION_MODE"]: self.logging.report_exception()
			finally:
				if len(tasks) > 0: await wait(tasks)

	async def check_price_alert(self, session, authorId, accountId, reference, alert):
		try:
			ticker = alert["request"].get("ticker")
			exchangeName = f" ({ticker.get('exchange').get('name')})" if ticker.get("exchange") else ''

			if alert["timestamp"] < time() - 86400 * 30.5 * 3:
				if environ["PRODUCTION_MODE"]:
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
				alert["request"]["timestamp"] = time()
				alert["request"]["authorId"] = authorId

				payload, message = {}, ""
				async with session.post(self.url + alert["currentPlatform"].lower(), json=alert["request"]) as response:
					data = await response.json()
					payload, message = data.get("response"), data.get("message")

				if not bool(payload):
					if message != "":
						print("Alert request error:", message)
						if environ["PRODUCTION_MODE"]: self.logging.report(message)
					return

				for candle in reversed(payload["candles"]):
					if candle[0] < alert["timestamp"]: break
					if (alert["placement"] == "below" and candle[3] is not None and candle[3] <= alert["level"]) or (alert["placement"] == "above" and candle[2] is not None and alert["level"] <= candle[2]):
						if environ["PRODUCTION_MODE"]:
							await database.document(f"discord/properties/messages/{str(uuid4())}").set({
								"title": f"Price of {ticker.get('name')}{exchangeName} hit {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')}.",
								"description": alert.get("triggerMessage"),
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
			if environ["PRODUCTION_MODE"]: self.logging.report_exception(user=f"{accountId}, {authorId}")


if __name__ == "__main__":
	environ["PRODUCTION_MODE"] = environ["PRODUCTION_MODE"] if "PRODUCTION_MODE" in environ and environ["PRODUCTION_MODE"] else ""
	alertsServer = AlertsServer()
	run(alertsServer.run())
