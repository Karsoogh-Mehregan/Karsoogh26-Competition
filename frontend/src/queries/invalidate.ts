/**
 * Start invalidation without joining it to the caller.
 *
 * A mutation's `onSuccess` is awaited before TanStack marks the mutation
 * successful, so returning an invalidation from one ties the button's pending
 * state to the refetches instead of to the request. A refetch pauses while the
 * tab is blurred or the device is offline (`retryer.canContinue`) and does not
 * resume until that changes, which leaves the button spinning with neither an
 * error nor a success even though the server already answered.
 */
export function detach(work: Promise<unknown> | Array<Promise<unknown>>): void {
  for (const promise of Array.isArray(work) ? work : [work]) {
    promise.catch(() => {})
  }
}
