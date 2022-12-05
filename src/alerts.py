from os import environ
environ["PRODUCTION"] = environ["PRODUCTION"] if "PRODUCTION" in environ and environ["PRODUCTION"] else ""

from signal import signal, SIGINT, SIGTERM
from time import time, mktime
from datetime import datetime, timedelta
from aiohttp import TCPConnector, ClientSession
from asyncio import sleep, wait, run, create_task
from orjson import dumps, OPT_SORT_KEYS
from uuid import uuid4
from pytz import utc, timezone
from traceback import format_exc

from discord import Webhook, Embed, File
from google.cloud.firestore import AsyncClient as FirestoreClient
from google.cloud.error_reporting import Client as ErrorReportingClient
from feedparser import parse

from Processor import process_chart_arguments, process_task
from DatabaseConnector import DatabaseConnector
from CommandRequest import CommandRequest
from helpers.utils import seconds_until_cycle, get_accepted_timeframes
from helpers.haltmap import HALT_MAP


database = FirestoreClient()
EST = timezone('US/Eastern')


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

		self.haltCache = {}
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
				await sleep(seconds_until_cycle())
				t = datetime.now().astimezone(utc)
				timeframes = get_accepted_timeframes(t)

				if "1m" in timeframes:
					await self.update_accounts()
					await wait([
						create_task(self.process_price_alerts()),
						create_task(self.process_halt_alerts()),
					])

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
								create_task(self.fetch_candles(session, alert.to_dict())),
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

	async def fetch_candles(self, session, alert):
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
						"backupChannel": alert.get("backupChannel"),
						"destination": alert.get("destination", 401328409499664394)
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
								"backupChannel": alert.get("backupChannel"),
								"destination": alert.get("destination", 401328409499664394)
							})
							await reference.delete()

						else:
							print(f"{accountId}: price of {ticker.get('name')}{exchangeName} hit {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')}")
						break

		except (KeyboardInterrupt, SystemExit): pass
		except Exception:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception(user=f"{accountId}, {authorId}")


	# -------------------------
	# Halt Alerts
	# -------------------------

	def parse_halt_date(self, date):
		return datetime.strptime(date, "%m/%d/%Y %H:%M:%S").replace(tzinfo=EST).timestamp()

	def parse_halts(self, data):
		parsed = {}
		for halt in data:
			resumption = None if halt["ndaq_resumptiondate"] == "" or halt["ndaq_resumptiontradetime"] == "" else self.parse_halt_date(halt["ndaq_resumptiondate"] + " " + halt["ndaq_resumptiontradetime"])
			if resumption is None or resumption > time():
				symbol = halt["ndaq_issuesymbol"].upper()
				if symbol in parsed:
					print("Duplicate halt:", symbol)
					if environ["PRODUCTION"]: self.logging.report(f"Duplicate halt: {symbol}")
					continue
				parsed[symbol] = {
					"timestamp" : self.parse_halt_date(halt["ndaq_haltdate"] + " " + halt["ndaq_halttime"]),
					"code": halt["ndaq_reasoncode"],
					"resumption": resumption,
					"hash": str(hash(f"{halt['ndaq_issuesymbol']}{halt['ndaq_haltdate']}{halt['ndaq_halttime']}{halt['ndaq_reasoncode']}{resumption}"))
				}
		return parsed

	async def process_halt_alerts(self):
		try:
			data = parse("http://www.nasdaqtrader.com/rss.aspx?feed=tradehalts")
			halts = self.parse_halts(data.entries)

			if self.haltCache.get("timestamp") is not None:
				new = set(halts.keys()).difference(set(self.haltCache["halts"].keys()))
			else:
				new = set()

			for symbol, halt in self.haltCache.get("halts", {}).items():
				if symbol not in halts or halts[symbol]["hash"] == halt["hash"]:
					continue
				new.add(symbol)

			self.haltCache = {
				"timestamp": time(),
				"halts": halts,
			}
			await database.document("details/halts").set(self.haltCache)

			startTimestamp = time()
			conn = TCPConnector(limit=5)
			async with ClientSession(connector=conn) as session:
				url = "https://discord.com/api/webhooks/1048157795830206514/MTBlZOqeYNTqeo0ocb9MoIBPzeIZzVmXPVJhrobbqzYkSx8luk6bOMF-kGBmcxyVuVLu"
				webhook = Webhook.from_url(url, session=session)

				for symbol in new:
					guildId = 414498292655980583

					guild = await self.guildProperties.get(guildId, {})
					accountId = guild.get("settings", {}).get("setup", {}).get("connection")
					user = await self.accountProperties.get(accountId, {})

					if not guild: await post.reference.delete()
					if guild.get("stale", {}).get("count", 0) > 0: continue

					request = CommandRequest(
						accountId=accountId,
						authorId=data["authorId"],
						channelId=data["channelId"],
						guildId=guildId,
						accountProperties=user,
						guildProperties=guild
					)

					platforms = request.get_platform_order_for("c")
					responseMessage, task = await process_chart_arguments([], platforms, tickerId=symbol)

					if responseMessage is not None:
						print(responseMessage)
						continue

					currentTask = task.get(task.get("currentPlatform"))
					timeframes = task.pop("timeframes")
					for p, t in timeframes.items(): task[p]["currentTimeframe"] = t[0]

					payload, responseMessage = await process_task(task, "chart")

					files, embeds = [], []
					if responseMessage == "requires pro":
						embed = Embed(title=f"The requested chart for `{currentTask.get('ticker').get('name')}` is only available on TradingView Premium.", description="All TradingView Premium charts are bundled with the [Advanced Charting add-on](https://www.alpha.bot/pro/advanced-charting).", color=constants.colors["gray"])
						embed.set_author(name="TradingView Premium", icon_url=static_storage.error_icon)
						embeds.append(embed)
					elif payload is None:
						errorMessage = f"Requested chart for `{currentTask.get('ticker').get('name')}` is not available." if responseMessage is None else responseMessage
						embed = Embed(title=errorMessage, color=constants.colors["gray"])
						embed.set_author(name="Chart not available", icon_url=static_storage.error_icon)
						embeds.append(embed)
					else:
						task["currentPlatform"] = payload.get("platform")
						currentTask = task.get(task.get("currentPlatform"))
						files.append(File(payload.get("data"), filename="{:.0f}-{}-{}.png".format(time() * 1000, request.authorId, randint(1000, 9999))))
						if halts[symbol]["resumption"] is None:
							embed = Embed(title=f"Trading for `{currentTask.get('ticker').get('name')}` has been halted.", description=f"Reason: {halts[symbol]['code']}\nNo resumption date", color=constants.colors["gray"])
						else:
							embed = Embed(title=f"Trading for `{currentTask.get('ticker').get('name')}` has been halted.", description=f"Reason: {halts[symbol]['code']}\n{datetime.strftime(datetime.fromtimestamp(halts[symbol]['resumption']), '%Y/%m/%d/ %H:%M:%S')}", color=constants.colors["gray"])

					await webhook.send(
						content=content,
						files=files,
						embeds=embeds,
						username="Alpha",
						avatar_url="https://cdn.discordapp.com/app-icons/401328409499664394/326e5bef971f8227de79c09d82031dda.png"
					)
		except (KeyboardInterrupt, SystemExit): pass
		except Exception:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception()


if __name__ == "__main__":
	alertsServer = AlertsServer()
	run(alertsServer.run())
