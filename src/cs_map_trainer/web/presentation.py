"""English UI labels shared by server-rendered pages and browser operations."""

from django.conf import settings

from cs_map_trainer.maps import SUPPORTED_MAP_LABELS, SUPPORTED_MAP_NAMES

from .billing import paid_access
from .entitlements import manual_access, monthly_limit
from .identity import verified_email
from .models import AccountPreferences
from .services import quota_used

STATES = {
    "uploading": "Waiting for your file",
    "queued": "Queued",
    "running": "Processing demo",
    "ready": "Report ready",
    "unsupported": "Unsupported demo",
    "failed": "Analysis failed",
    "expired": "Upload expired",
}
ERRORS = {
    "verified_email_required": "Verify your email address to continue.",
    "account_blocked": "Your account is blocked. Contact support.",
    "invalid_player_steam_id": "Enter a SteamID64 consisting of exactly 17 digits.",
    "monthly_demo_limit": (
        "You have used your free analysis allowance for this UTC calendar month. "
        "Wait until next month or upgrade to Pro."
    ),
    "billing_not_configured": "Payments are not available yet. Contact the administrator.",
    "billing_unavailable": "Stripe is unavailable. The action was not confirmed. Please try again.",
    "billing_invalid_response": "We could not confirm Stripe's response. Please try again later.",
    "billing_price_mismatch": (
        "The Stripe price does not match the $7.99/month plan. Contact the administrator."
    ),
    "billing_portal_mismatch": (
        "The billing portal is not configured correctly. Contact the administrator."
    ),
    "billing_subscription_mismatch": (
        "The subscription is not configured correctly. Contact the administrator."
    ),
    "billing_customer_required": "Start a subscription purchase before opening the billing portal.",
    "billing_account_closed": "This billing account has been closed.",
    "subscription_already_exists": (
        "You already have a subscription. Open Manage subscription in Stripe to check it."
    ),
    "active_upload_exists": "An upload or analysis is already active. Check My analyses.",
    "input_cleanup_pending": (
        "Your previous demo is still being deleted. Wait before uploading another."
    ),
    "storage_unavailable": "File storage is unavailable. Please try again later.",
    "storage_not_configured": "File storage is not configured. Contact the administrator.",
    "upload_expired": "Your upload reservation has expired. Start a new upload.",
    "invalid_uploaded_object": (
        "We could not verify the uploaded file. Return to the upload page and try again."
    ),
    "invalid_demo_size": "Choose an uncompressed .dem file between 8 bytes and 1 GiB.",
    "upload_rights_confirmation_required": "Confirm that you have permission to upload this demo.",
    "idempotency_conflict": (
        "This upload reservation belongs to a different file or SteamID. Use the original values."
    ),
    "unsupported_or_invalid_demo": (
        f"This file is invalid or unsupported. Choose a CS2 demo from: {SUPPORTED_MAP_LABELS}."
    ),
    "linked_player_not_in_demo": (
        "The selected SteamID was not found in this demo. Check the ID before uploading again. "
        "This analysis attempt counts toward your monthly limit."
    ),
    "worker_lost": (
        "Analysis was interrupted. It will not restart automatically. Upload again to retry."
    ),
    "processing_failed": "Analysis failed. Upload the demo again to start a new attempt.",
    "processing_in_progress": "Wait for the active analysis to finish before deleting.",
    "password_confirmation_required": "Enter your correct password to delete your account.",
    "result_not_ready": "Your result is not ready yet.",
    "invalid_saved_report": "The saved report is invalid. Contact the administrator.",
    "invalid_saved_selection": (
        "The saved scenario selection is invalid. Contact the administrator."
    ),
    "no_training_candidates": "No eligible lost duels were found for practice.",
    "invalid_scenario_selection": (
        "Select at least one scenario. Your selection has not been saved."
    ),
    "invalid_selection_payload": (
        "This scenario selection is invalid. Refresh the report and try again."
    ),
    "scenario_not_exportable": (
        "One or more selected scenarios cannot be exported. No selection was saved. "
        "Check their data and explicitly uncheck unsupported scenarios, then retry."
    ),
    "scenario_not_found": "This scenario was not found in the report.",
    "invalid_practice_rating": "Choose one of the available practice ratings.",
    "invalid_practice_filter": "This practice filter is invalid. Choose a tab in Practice.",
    "not_found": "This private result was not found.",
    "delete_confirmation_required": "Select the checkbox to confirm permanent deletion.",
    "invalid_json": "The request could not be read. Refresh the page and try again.",
    "invalid_json_object": "The request format is invalid. Refresh the page and try again.",
    "invalid_request_id": "The upload request is invalid. Refresh the page and try again.",
    "invalid_export_parameters": "The download options are invalid. Return to the practice page.",
}
LIMITATIONS = {
    "map_geometry_unverified": "Map geometry compatibility has not been verified.",
    "contact_inferred_from_damage": (
        "The start of the exchange is estimated from damage, not first visual contact."
    ),
    "static_positions_only": "Only static positions are reconstructed.",
    "smoke_visibility_not_evaluated": "Visibility through smoke has not been evaluated.",
    "movement_not_reconstructed": "Player movement is not reconstructed.",
    "health_armor_not_reconstructed": "Health and armor are not reconstructed.",
    "bot_behavior_not_reconstructed": "The bot does not reproduce the opponent's behavior.",
    "roll_not_recorded": "View roll was not measured and is set to zero.",
    "opponent_aim_inferred_toward_player": (
        "Missing opponent aim angles are estimated toward the player, assuming equal eye heights."
    ),
    "player_blinded": "The player was flashed at the snapshot.",
    "opponent_blinded": "The opponent was flashed at the snapshot.",
    "player_flash_unknown": "The player's flash status is unknown.",
    "opponent_flash_unknown": "The opponent's flash status is unknown.",
    "player_posture_unknown": "The player's crouch or jump status is unknown.",
    "opponent_posture_unknown": "The opponent's crouch or jump status is unknown.",
    "penetration_unknown": "Whether the final shot penetrated a surface is unknown.",
    "through_smoke_unknown": "Whether the final shot passed through smoke is unknown.",
    "ranking_is_loss_frequency_not_win_rate": "Groups are ranked by losses, not win rate.",
    "win_rate_only_covers_filtered_resolved_duels": (
        "Win rate covers only filtered duels with a recorded kill or death."
    ),
    "unresolved_encounters_and_exposure_not_measured": (
        "Encounters without a kill or death and time exposed to opponents are not measured."
    ),
    "small_samples_do_not_establish_skill": "Small samples do not establish player skill.",
    "grid_groups_are_heuristic": (
        "Position-based groups are approximate, not verified tactical categories."
    ),
    "console_export_not_verified": "Console commands have not been verified in game.",
}
EXCLUSIONS = {
    "outside_live_round": "Outside a live round",
    "knife_round": "Knife round",
    "world_or_suicide": "Environmental death or suicide",
    "unknown_side": "Unknown team",
    "teamkill": "Team kill",
    "unsupported_killing_weapon": "Unsupported weapon used for the kill",
    "penetration": "Shot through a surface",
    "through_smoke": "Shot through smoke",
    "missing_damage_contact": "No qualifying damage exchange found",
    "no_pre_contact_live_tick": "No live-round snapshot before the exchange",
    "multi_party_damage": "Damage exchange involved additional players",
    "missing_shared_snapshot": "No shared snapshot for both players",
    "snapshot_side_mismatch": "Snapshot teams do not match the duel",
    "unknown_snapshot_side": "Unknown team in the snapshot",
    "missing_or_dead_snapshot_participant": "A player is missing or dead in the snapshot",
    "unsupported_posture": "Crouching or jumping is not supported",
    "unsupported_snapshot_weapon": "Unsupported weapon in the snapshot",
    "missing_snapshot_position_or_angles": "Missing position or aim angles",
    "invalid_snapshot_values": "Invalid snapshot data",
    "undefined_opponent_aim_direction": "Opponent aim direction cannot be estimated",
}
EXPORT_DETAILS = {
    "isolated_local_session_one_human": "Use an isolated local session with one human player.",
    "bot_player_index_2_after_bot_kick_unverified": (
        "Bot player index 2 after removing existing bots is assumed, not verified."
    ),
    "bot_pawn_entity_index_2_unverified_separate_from_player_index": (
        "Bot pawn entity index 2 is a separate, unverified assumption from the player index."
    ),
    "bot_spawn_and_jointeam_ready_before_next_command_unverified": (
        "Bot spawn and team readiness before the next command have not been verified."
    ),
    "point_teleport_sets_bot_eye_angles_unverified": (
        "Whether point_teleport sets the bot's eye angles has not been verified."
    ),
    "console_entity_io_and_yprac_chat_ordering_unverified": (
        "Console, entity I/O and Yprac chat execution order has not been verified."
    ),
    "yprac_weapon_identifiers_and_active_weapon_unverified": (
        "Yprac weapon identifiers and active weapon selection have not been verified."
    ),
    "target_map_geometry_and_client_access_unverified": (
        "Map geometry compatibility and client access have not been verified."
    ),
    "helper_entity_creation_and_cleanup_ordering_unverified": (
        "Helper entity creation and cleanup order has not been verified."
    ),
    "sv_cheats=1": "Enables cheat commands (sv_cheats=1).",
    "mp_limitteams=0": "Disables the team size difference limit (mp_limitteams=0).",
    "mp_autoteambalance=0": "Disables automatic team balancing (mp_autoteambalance=0).",
    "bot_quota_mode=normal": "Sets the bot quota mode to normal.",
    "bot_quota=0_before_adding_one_bot": "Sets the bot quota to zero before adding one bot.",
    "bot_stop=1": "Stops bot movement (bot_stop=1).",
    "all_existing_bots_kicked": "Kicks all existing bots.",
    "human_team_position_angles_and_weapon_changed": (
        "Changes your team, position, aim angles and weapon."
    ),
    "entity_index_2_targetname_changed": "Changes the target name of entity index 2.",
    "cmt_v1_teleport_created_and_removed": "Creates and removes the cmt_v1_teleport helper entity.",
}


def error_message(code):
    return ERRORS.get(code, f"The action failed. Error code: {code}")


def ui_context(request):
    last_player_steam_id = ""
    used = None
    paid = False
    manual = False
    manual_until = None
    limit = settings.DEMO_MONTHLY_LIMIT
    if request.user.is_authenticated:
        last_player_steam_id = (
            AccountPreferences.objects.filter(owner=request.user)
            .values_list("last_player_steam_id", flat=True)
            .first()
            or ""
        )
        used = quota_used(request.user)
        paid = paid_access(request.user)
        manual = manual_access(request.user)
        limit = monthly_limit(request.user)
        if manual:
            manual_until = request.user.account_policy.manual_pro_until
    errors = dict(ERRORS)
    if request.user.is_authenticated:
        errors["monthly_demo_limit"] = (
            f"You have used your {limit} free analyses for this UTC calendar month. "
            "Wait until next month or upgrade to Pro."
        )
    return {
        "supported_map_labels": SUPPORTED_MAP_LABELS,
        "supported_map_names": SUPPORTED_MAP_NAMES,
        "last_player_steam_id": last_player_steam_id,
        "email_verified": verified_email(request.user),
        "quota_used": used,
        "quota_limit": limit,
        "quota_remaining": max(0, limit - used) if used is not None else None,
        "paid_plan": paid or manual,
        "stripe_paid_plan": paid,
        "manual_pro": manual,
        "manual_pro_until": manual_until,
        "ui_errors": errors,
    }
