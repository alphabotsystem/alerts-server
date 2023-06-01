HALT_MAP = {
	"T1": {
		"title": "News pending",
		"description": "Trading has been halted because there is material news pending for the security.",
		"chart": "high"
	},
	"T2": {
		"title": "News released",
		"description": "The dissemination process of the news has commenced using compliant methods."
	},
	"T3": {
		"title": "Resumption time announced",
		"description": "The news has been fully disseminated or NASDAQ has resolved any issues causing market extraordinary activity. Trading resumption time has been announced.",
		"chart": "high"
	},
	"T5": {
		"title": "Single stock trading pause",
		"description": "Trading has halted due to a 10% or more price movement in the security within a five-minute timeframe.",
		"chart": "low"
	},
	"T6": {
		"title": "Extraordinary market activity",
		"description": "Trading has halted because NASDAQ determined that extraordinary market activity, likely to affect the market for a security, is caused by system misuse or malfunction linked to NASDAQ or another trading facility.",
		"chart": "low"
	},
	"T7": {
		"title": "Quotation-only period",
		"description": "Quotations have resumed for affected security, but trading remains paused."
	},
	"T8": {
		"title": "ETF trading halt",
		"description": "Trading in an ETF may be halted based on several factors, including trading activity in underlying securities, halts/suspensions in primary markets, or unusual conditions that affect market fairness and orderliness.",
		"chart": "high"
	},
	"T12": {
		"title": "Additional information requested",
		"description": "Trading has halted until additional requested information is received by NASDAQ.",
		"chart": "high"
	},
	"H4": {
		"title": "Non-compliance",
		"description": "Trading has halted due to the company's non-compliance with NASDAQ listing requirements.",
		"chart": "high"
	},
	"H9": {
		"title": "Not current",
		"description": "Trading has halted because the company is not current in its required filings.",
		"chart": "high"
	},
	"H10": {
		"title": "SEC trading suspension",
		"description": "The Securities and Exchange Commission has suspended trading in this stock.",
		"chart": "high"
	},
	"H11": {
		"title": "Regulatory concern",
		"description": "Trading has halted in conjunction with another exchange or market for regulatory reasons.",
		"chart": "high"
	},
	"O1": {
		"title": "Operations halt",
		"description": "Contact market operations for more information."
	},
	"IPO1": {
		"title": "IPO listed",
		"description": "An IPO has been listed on NASDAQ, but trading has not yet commenced.",
		"halt": False
	},
	"IPOQ": {
		"title": "IPO released for quotation",
		"description": "An IPO security has been released for quotation and is expected to commence trading shortly.",
		"halt": False
	},
	"IPOE": {
		"title": "IPO positioning window extension",
		"halt": False
	},
	"M": {
		"title": "Volatility trading pause",
		"description": "Trading has been halted due to market manipulation.",
		"chart": "low"
	},
	"M1": {
		"title": "Corporate action",
		"description": "Trading has halted due to a significant event related to the company, such as mergers, acquisitions, stock splits, or dividend announcements, which may impact the stock's price or trading volume.",
		"chart": "high"
	},
	"M2": {
		"title": "Quotation not available",
		"description": "Trading has halted due to stock's quotation not being available due to technical issues or a lack of market makers providing quotes.",
		"chart": "low"
	},
	"LUDP": {
		"title": "Volatility trading pause",
		"description": "Trading has halted due to extreme stock price movement or high volatility in a short period to allow the market to stabilize.",
		"chart": "low"
	},
	"LUDS": {
		"title": "Volatility Trading Pause - Straddle Condition",
		"description": "Trading has halted due to extreme stock price movement or high volatility because of a straddle condition, typically related to options trading.",
		"chart": "low"
	},
	"MWC0": {
		"title": "Market Wide Circuit Breaker Halt - Carry over from previous day",
		"description": "Trading has halted due to a market-wide circuit breaker triggered on the previous day, which has not been resolved.",
		"halt": False
	},
	"MWC1": {
		"title": "Market Wide Circuit Breaker Halt - Level 1",
		"description": "A temporary halt in trading for all stocks when the market experiences a 7% drop from the previous day's closing price.",
		"halt": False
	},
	"MWC2": {
		"title": "Market Wide Circuit Breaker Halt - Level 2",
		"description": "A temporary halt in trading for all stocks when the market experiences a 13% drop from the previous day's closing price.",
		"halt": False
	},
	"MWC3": {
		"title": "Market Wide Circuit Breaker Halt - Level 3",
		"description": "Trading has halted for all stocks for the rest of the day when the market experiences a 20% drop from the previous day's closing price.",
		"halt": False
	},
	"MWCQ": {
		"title": "Market Wide Circuit Breaker Resumption",
		"description": "Trading has resumed after a market-wide circuit breaker halt.",
		"halt": False
	},
	"R4": {
		"title": "Qualifications Issues Reviewed/Resolved - Quotations/Trading to Resume",
		"description": "A halt in trading lifted after reviewing or resolving any qualification issues with the stock, allowing quotations or trading to resume.",
		"chart": "high"
	},
	"R9": {
		"title": "Filing Requirements Satisfied/Resolved - Quotations/Trading to Resume",
		"description": "A halt in trading lifted after satisfying or resolving any filing requirements, allowing quotations or trading to resume.",
		"chart": "high"
	},
	"C3": {
		"title": "Issuer News Not Forthcoming - Quotations/Trading to Resume",
		"description": "A halt in trading lifted when no significant news is expected from the issuer, allowing quotations or trading to resume.",
		"chart": "high"
	},
	"C4": {
		"title": "Qualifications Halt Ended",
		"description": "A halt in trading lifted after a qualifications halt has ended, and the stock has met maintenance requirements, allowing trading to resume.",
		"chart": "high"
	},
	"C9": {
		"title": "Qualifications Halt Concluded - Filings Met - Quotations/Trading to Resume",
		"description": "A halt in trading lifted after a qualifications halt has concluded, and required filings have been met, allowing quotations and trading to resume.",
		"chart": "high"
	},
	"C11": {
		"title": "Trade Halt Concluded By Other Regulatory Auth,; Quotations/Trading to Resume",
		"description": "A halt in trading lifted by another regulatory authority, allowing quotations and trading to resume.",
		"chart": "high"
	}
	# "R1": {
	# 	"title": "New Issue Available",
	# 	"description": "A notification that a new stock issue is available for trading.",
	# 	"chart": "high"
	# },
	# "R2": {
	# 	"title": "Issue Available",
	# 	"description": "A notification that an existing stock issue is available for trading."
	# },
	# "D": {
	# 	"title": "Security deletion from NASDAQ / CQS",
	# 	"description": "A notification that a security has been removed or delisted from NASDAQ or the Consolidated"
	# },
}