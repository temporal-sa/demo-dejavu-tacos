import { useCallback, useEffect, useState } from 'react'

interface StoreOrder {
  order_id: string
  items: { name: string; quantity: number }[]
  total: number
  status: string
  created_at: string
}

export function KitchenDisplay() {
  const [orders, setOrders] = useState<StoreOrder[]>([])
  const [storeOnline, setStoreOnline] = useState(true)

  const fetchStatus = useCallback(() => {
    Promise.all([
      fetch('/api/store/orders').then((r) => r.json()),
      fetch('/api/store/status').then((r) => r.json()),
    ]).then(([ordersData, statusData]) => {
      setOrders(ordersData)
      setStoreOnline(statusData.online)
    })
  }, [])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 2000)
    return () => clearInterval(interval)
  }, [fetchStatus])

  const handlePlugIn = async () => {
    await fetch('/api/store/go-online', { method: 'POST' })
    setStoreOnline(true)
  }

  const handleUnplug = async () => {
    await fetch('/api/store/go-offline', { method: 'POST' })
    setStoreOnline(false)
  }

  const handleMarkReady = async (orderId: string) => {
    await fetch(`/api/store/order-ready/${orderId}`, { method: 'POST' })
    fetchStatus()
  }

  // Store offline overlay
  if (!storeOnline) {
    return (
      <div className="flex-1 bg-gray-900 flex items-center justify-center">
        <div className="text-center max-w-md px-8">
          {/* Funny ethernet animation */}
          <div className="mb-6 relative">
            <div className="text-8xl mb-4">🔌</div>
            <div className="absolute -top-2 -right-8 text-4xl animate-bounce">💥</div>
          </div>

          <h1 className="text-2xl font-bold text-red-400 mb-2">
            Connection Lost!
          </h1>
          <p className="text-lg text-gray-300 mb-2">
            Uh oh... Bob accidentally unplugged the ethernet again!
          </p>
          <p className="text-sm text-gray-500 mb-8">
            The kitchen display system has lost its connection to the network.
            All pending orders are queued and waiting.
          </p>

          {/* Plug it back in button */}
          <button
            onClick={handlePlugIn}
            className="group relative inline-flex items-center gap-3 px-8 py-4 bg-green-600 text-white rounded-2xl font-bold text-lg hover:bg-green-500 active:scale-95 transition-all shadow-lg shadow-green-600/30"
          >
            <span className="text-2xl group-hover:animate-bounce">🔌</span>
            Plug It Back In
          </button>

          <p className="text-xs text-gray-600 mt-4 italic">
            (This is fine. Everything is fine.)
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 bg-gray-900 flex flex-col">
      {/* KDS Header */}
      <div className="bg-gray-800 border-b border-gray-700 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl">🖥️</span>
          <div>
            <h1 className="text-lg font-bold text-gray-200">
              Kitchen Display System
            </h1>
            <p className="text-xs text-gray-400">Déjà Vu Tacos #42</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-green-400 font-medium">Online</span>
          </div>
          <button
            onClick={handleUnplug}
            className="group inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 text-gray-200 rounded-lg text-xs font-bold hover:bg-red-600 hover:text-white active:scale-95 transition-all"
          >
            <span className="group-hover:animate-bounce">🔌</span>
            Unplug the Cable Again
          </button>
        </div>
      </div>

      {/* Orders grid */}
      <div className="flex-1 overflow-y-auto p-4">
        {orders.length === 0 ? (
          <div className="text-center py-20">
            <span className="text-6xl block mb-4">🌮</span>
            <p className="text-gray-500 text-lg">Waiting for orders...</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {orders.map((order) => (
              <div
                key={order.order_id}
                className={`rounded-xl border-2 p-4 ${
                  order.status === 'ready'
                    ? 'border-green-500 bg-green-500/10'
                    : order.status === 'preparing' || order.status === 'pending'
                      ? 'border-yellow-500 bg-yellow-500/10'
                      : 'border-gray-700 bg-gray-800'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-gray-200 font-mono">
                    #{order.order_id.slice(0, 6).toUpperCase()}
                  </h3>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      order.status === 'ready'
                        ? 'bg-green-500/20 text-green-300'
                        : order.status === 'preparing' || order.status === 'pending'
                          ? 'bg-yellow-500/20 text-yellow-300'
                          : 'bg-gray-700 text-gray-400'
                    }`}
                  >
                    {order.status === 'ready'
                      ? 'READY'
                      : order.status === 'preparing' || order.status === 'pending'
                        ? 'PREPARING'
                        : order.status.toUpperCase()}
                  </span>
                </div>

                {/* Items */}
                <div className="space-y-1 mb-3">
                  {order.items.map((item, i) => (
                    <p key={i} className="text-sm text-gray-300">
                      {item.quantity}x {item.name}
                    </p>
                  ))}
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">
                    ${order.total.toFixed(2)}
                  </span>

                  {order.status !== 'ready' &&
                    order.status !== 'failed' &&
                    order.status !== 'completed' && (
                      <button
                        onClick={() => handleMarkReady(order.order_id)}
                        className="px-4 py-1.5 bg-green-600 text-white rounded-lg text-sm font-bold hover:bg-green-500 active:scale-95 transition-all"
                      >
                        Mark Ready
                      </button>
                    )}

                  {order.status === 'ready' && (
                    <span className="text-green-400 font-bold text-sm">
                      ✓ Done
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
