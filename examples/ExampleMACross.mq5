//+------------------------------------------------------------------+
//| ExampleMACross.mq5                                                |
//| Experto de ejemplo para el modo probador del laboratorio:         |
//| cruce de medias con stop por ATR. No es una recomendación.        |
//+------------------------------------------------------------------+
#property version "1.00"
#include <Trade\Trade.mqh>

input int    InpFast    = 20;      // Media rápida
input int    InpSlow    = 100;     // Media lenta
input double InpATRMult = 3.0;     // Stop = ATR × factor
input double InpRiskPct = 0.5;     // % del capital en riesgo por operación
input long   InpMagic   = 1001;    // Número mágico

CTrade g_trade;
int    g_fast, g_slow, g_atr;
datetime g_lastBar = 0;

int OnInit()
  {
   g_fast = iMA(_Symbol, PERIOD_H4, InpFast, 0, MODE_SMA, PRICE_CLOSE);
   g_slow = iMA(_Symbol, PERIOD_H4, InpSlow, 0, MODE_SMA, PRICE_CLOSE);
   g_atr  = iATR(_Symbol, PERIOD_H4, 14);
   if(g_fast == INVALID_HANDLE || g_slow == INVALID_HANDLE || g_atr == INVALID_HANDLE)
      return INIT_FAILED;
   g_trade.SetExpertMagicNumber(InpMagic);
   return INIT_SUCCEEDED;
  }

double LotFor(double slDist)
  {
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(tv <= 0 || ts <= 0 || step <= 0 || slDist <= 0) return 0.0;
   double lot = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPct / 100.0 / (slDist / ts * tv);
   lot = MathFloor(lot / step) * step;
   return MathMax(lot, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN));
  }

void OnTick()
  {
   datetime bt = iTime(_Symbol, PERIOD_H4, 0);
   if(bt == g_lastBar) return;
   g_lastBar = bt;

   double f[2], s[2], a[1];
   if(CopyBuffer(g_fast, 0, 1, 2, f) != 2 || CopyBuffer(g_slow, 0, 1, 2, s) != 2 || CopyBuffer(g_atr, 0, 1, 1, a) != 1)
      return;
   int dir = 0;
   if(f[0] <= s[0] && f[1] > s[1]) dir = +1;   // f[1] es la vela cerrada más reciente
   if(f[0] >= s[0] && f[1] < s[1]) dir = -1;
   if(dir == 0) return;

   // cierra la posición contraria y abre a favor del cruce
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetInteger(POSITION_MAGIC) == InpMagic && PositionGetString(POSITION_SYMBOL) == _Symbol)
         g_trade.PositionClose(tk);
     }
   double sl = InpATRMult * a[0];
   double lot = LotFor(sl);
   if(lot <= 0) return;
   if(dir > 0)
      g_trade.Buy(lot, _Symbol, 0, SymbolInfoDouble(_Symbol, SYMBOL_ASK) - sl, 0, "lab");
   else
      g_trade.Sell(lot, _Symbol, 0, SymbolInfoDouble(_Symbol, SYMBOL_BID) + sl, 0, "lab");
  }
//+------------------------------------------------------------------+
