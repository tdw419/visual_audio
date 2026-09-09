#![no_std]
#![no_main]
extern crate alloc;
use uefi::prelude::*;
#[global_allocator]
static ALLOCATOR: uefi::allocator::Allocator = uefi::allocator::Allocator;
#[entry]
fn main() -> Status { Status::SUCCESS }
