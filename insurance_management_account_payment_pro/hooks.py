def post_init_hook(env):
    """Draft payments of installments created before this module: their debts
    were auto-filled with every open line of the insurer. Keep only the
    installment line."""
    installments = env["insurance.installment"].sudo().search(
        [("payment_id.state", "=", "draft"), ("move_line_id", "!=", False)]
    )
    installments._set_payment_debt()
